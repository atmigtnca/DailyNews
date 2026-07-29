import os
import json
import re
from urllib.parse import urlparse

import requests

# --- 환경 변수 가져오기 ---
webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
file_path = os.environ.get('FILE_PATH')

if not webhook_url or not file_path:
    print("Error: 필수 환경 변수(SLACK_WEBHOOK_URL, FILE_PATH)가 없습니다.")
    exit(1)

# --- 카테고리별 헤더 설정 ---
if "논문" in file_path:
    category = "논문 요약"
    main_header = "📚 오늘의 논문 요약이 도착했습니다!"
elif "프로덕트" in file_path:
    category = "프로덕트 뉴스"
    main_header = "🚀 오늘의 프로덕트 뉴스가 도착했습니다!"
else:
    category = "뉴스레터"
    main_header = "📰 오늘의 뉴스레터가 도착했습니다!"

# --- 파일 읽기 ---
try:
    with open(file_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
except FileNotFoundError:
    print(f"Error: 파일을 찾을 수 없습니다 -> {file_path}")
    exit(1)

# --- Slack 전송 ---

def send_payload(payload):
    response = requests.post(
        webhook_url,
        data=json.dumps(payload),
        headers={'Content-Type': 'application/json'}
    )
    if response.status_code != 200:
        print(f"❌ Slack Error: {response.text}")
        print("--- Sent Payload (Debugging) ---")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        exit(1)

def send_blocks(all_blocks):
    # Slack 메시지당 블록 50개 제한 → 초과 시 여러 메시지로 나눠 전송
    for i in range(0, len(all_blocks), 50):
        send_payload({"blocks": all_blocks[i:i + 50]})
    print(f"✅ Slack 전송 완료 (블록 {len(all_blocks)}개)")

# --- 리포트 유효성 검사 ---
# upstream 생성 파이프라인이 실패하면 실제 리포트 대신 LLM의 되묻는 응답이나
# 오류 안내문이 그대로 커밋됨. 그런 파일은 아무것도 보내지 않고 조용히 건너뜀.
BROKEN_OPENINGS = [
    "죄송", "안녕하세요", "안내드립니다", "요청하신", "요청해주신",
    "요청 감사", "이미 여러", "알려주",
]

def is_broken_report(content):
    head = content.lstrip()[:30]
    if any(p in head for p in BROKEN_OPENINGS):
        return True
    # 정상 리포트는 항상 기사/논문 링크나 이미지를 포함함 (깨진 리포트는 전부 0개)
    return len(re.findall(r'\]\(http', content)) == 0

if is_broken_report(md_content):
    print(f"⚠️ 깨진 리포트 감지({category}), Slack 전송 안 함 -> {file_path}")
    exit(0)

# --- URL 헬퍼 ---

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')

def is_usable_url(url):
    # upstream이 URL을 중간에서 잘라먹는 경우가 있어(공백/… 포함, 비ASCII) 걸러냄
    if not url or not url.startswith('http'):
        return False
    if re.search(r'\s|\.\.\.', url) or not url.isascii():
        return False
    return True

def is_image_url(url):
    # 인스타그램 CDN처럼 쿼리스트링이 붙은 URL도 경로 확장자로 판별
    path = urlparse(url).path.lower()
    return path.endswith(IMAGE_EXTENSIONS)

def image_actually_loads(url):
    # upstream이 서명 파라미터를 잘라먹은 CDN URL은 403이 남.
    # Slack은 로드 안 되는 image 블록이 있으면 메시지 전체를 거부하므로 사전 확인.
    try:
        r = requests.get(url, timeout=5, stream=True,
                         headers={'User-Agent': 'Mozilla/5.0'})
        ok = r.status_code == 200 and r.headers.get('Content-Type', '').startswith('image/')
        r.close()
        return ok
    except requests.RequestException:
        return False

def clean_markdown(text):
    text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)  # 굵게
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<\2|\1>', text)  # 링크
    text = text.replace("**", "")
    return text

def escape_mrkdwn(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def append_section(blocks, text):
    # 3000자 블록 제한에 맞춰 문단 경계에서 분할
    text = text.strip()
    LIMIT = 2900
    while len(text) > LIMIT:
        split_index = text.rfind('\n', 0, LIMIT)
        if split_index <= 0:
            split_index = LIMIT
        chunk = text[:split_index].strip()
        if chunk:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk}})
        text = text[split_index:].strip()
    if text:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})

# --- 1차: 구조적 파싱 (제목/요약/쉬운설명/관련분야/중요도·추천수/링크) ---

FIELD_KEYS = ('요약', '쉬운설명', '관련분야', '중요도', '추천수', '전체링크', 'PDF 다운로드 링크')

def parse_items(content):
    items = []
    for chunk in re.split(r'\n\s*---\s*\n', content):
        fields = {}
        images = []
        file_url = None
        current_key = None
        for raw in chunk.split('\n'):
            line = raw.strip()
            if line.startswith("다음 단계 제안"):
                break
            if line.startswith("(주의"):
                continue

            # 이미지/파일 마크다운을 먼저 분리
            img = re.search(r'!\[(.*?)\]\((.*?)\)', line)
            if img:
                url = img.group(2).strip()
                if is_usable_url(url):
                    if is_image_url(url):
                        images.append(url)
                    else:
                        file_url = url
                line = (line[:img.start()] + line[img.end():]).strip()
            elif line.startswith('!['):
                continue  # 닫는 괄호도 없이 잘린 이미지 → 버림

            heading = re.match(r'^#{1,6}\s*(.+?)\s*$', line)
            if heading:
                line = heading.group(1)

            key_match = re.match(
                r'^\*?\*?(' + '|'.join(FIELD_KEYS) + r'|제목)\*?\*?\s*:\s*(.*)$', line)
            if key_match:
                current_key = key_match.group(1)
                fields[current_key] = key_match.group(2).strip()
            elif line and current_key:
                fields[current_key] = (fields[current_key] + '\n' + line).strip()
        if fields.get('제목') and fields.get('요약'):
            items.append({'fields': fields, 'images': images, 'file_url': file_url})

    # 파일이 생성 도중 잘리면 마지막 항목이 제목·요약 일부만 남음.
    # 정상 항목은 항상 메타 필드(관련분야/중요도/추천수/링크) 중 하나 이상을 가지므로
    # 그게 전무한 꼬리 항목은 잘린 것으로 보고 조용히 제외.
    META_KEYS = ('관련분야', '중요도', '추천수', '전체링크', 'PDF 다운로드 링크')
    while items and not any(k in items[-1]['fields'] for k in META_KEYS):
        items.pop()
    return items

def build_structured_blocks(items):
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": main_header, "emoji": True}},
    ]
    for i, item in enumerate(items, 1):
        f = item['fields']
        if i > 1:
            blocks.append({"type": "divider"})

        # 항목 대표 이미지 (실제 로드되는 경우에만)
        if item['images'] and image_actually_loads(item['images'][0]):
            blocks.append({
                "type": "image",
                "image_url": item['images'][0],
                "alt_text": f['제목'][:100],
            })

        # 제목: 원문 링크가 있으면 제목 자체를 링크로
        title = escape_mrkdwn(re.sub(r'\s+', ' ', f['제목']))
        link = None
        for key in ('전체링크', 'PDF 다운로드 링크'):
            m = re.search(r'https?://\S+', f.get(key, ''))
            if m and is_usable_url(m.group(0)):
                link = m.group(0)
                break
        link = link or item['file_url']
        title_line = f"*<{link}|{i}. {title}>*" if link else f"*{i}. {title}*"

        text = f"{title_line}\n{clean_markdown(f['요약'])}"
        if f.get('쉬운설명'):
            easy = re.sub(r'\s+', ' ', clean_markdown(f['쉬운설명'])).strip()
            text += f"\n\n_💡 {easy}_"
        append_section(blocks, text)

        # 메타 정보는 작은 회색 글씨(context)로
        meta = []
        if f.get('관련분야'):
            topics = [t.strip(' -·•') for t in f['관련분야'].split('\n') if t.strip(' -·•')]
            meta.append(' · '.join(topics))
        if f.get('중요도'):
            m = re.search(r'\d+', f['중요도'])
            if m:
                meta.append(f"중요도 {m.group(0)}/10")
        if f.get('추천수'):
            m = re.search(r'\d+', f['추천수'])
            if m:
                meta.append(f"👍 {m.group(0)}")
        if meta:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": "   ·   ".join(meta)}],
            })
    return blocks

# --- 2차(폴백): 일반 라인 단위 변환 ---

def build_generic_blocks(content):
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": main_header, "emoji": True}},
        {"type": "divider"},
    ]
    buffer = []

    def flush():
        if buffer:
            append_section(blocks, '\n'.join(buffer))
            buffer.clear()

    bold_next_line = False
    for line in content.split('\n'):
        line = line.strip()
        if line.startswith("다음 단계 제안"):
            break
        if line.startswith("(주의"):
            continue

        img_match = re.search(r'!\[(.*?)\]\((.*?)\)', line)
        if img_match:
            alt_text, url = img_match.group(1).strip(), img_match.group(2).strip()
            if is_usable_url(url) and is_image_url(url):
                if image_actually_loads(url):
                    flush()
                    blocks.append({"type": "image", "image_url": url,
                                   "alt_text": alt_text or "News Image"})
            elif is_usable_url(url):
                buffer.append(f"📄 <{url}|{alt_text or '파일 보기'}>")
            # 잘린/깨진 URL은 표시할 방법이 없으므로 조용히 버림
        elif line.startswith('![') or line.startswith('https://scontent'):
            continue
        elif line == '---':
            flush()
            blocks.append({"type": "divider"})
        elif line.startswith('##'):
            flush()
            heading = clean_markdown(line.lstrip('#').strip())
            if heading.startswith('제목:'):
                heading = heading[len('제목:'):].strip()
            if heading:
                buffer.append(f"*{heading}*")
            else:
                bold_next_line = True
        elif line:
            cleaned = clean_markdown(line)
            if cleaned:
                if bold_next_line:
                    cleaned = f"*{cleaned}*"
                    bold_next_line = False
                buffer.append(cleaned)
    flush()

    # 파일이 중간에서 잘려 제목만 남은 꼬리 항목 등 정리
    def is_dangling(block):
        if block["type"] in ("divider", "image"):
            return True
        if block["type"] == "section":
            return re.fullmatch(r'\*[^\n*]+\*', block["text"]["text"].strip()) is not None
        return False

    while len(blocks) > 2 and is_dangling(blocks[-1]):
        blocks.pop()
    return blocks

# --- 변환 및 전송 ---

items = parse_items(md_content)
if items:
    print(f"구조적 파싱 성공: {len(items)}개 항목")
    blocks = build_structured_blocks(items)
else:
    print("구조적 파싱 실패 → 일반 변환으로 폴백")
    blocks = build_generic_blocks(md_content)

if len(blocks) <= 2:
    print(f"⚠️ 전송할 본문이 없습니다({category}), Slack 전송 안 함 -> {file_path}")
    exit(0)

print(f"🚀 Sending file: {file_path} (Blocks: {len(blocks)})")
send_blocks(blocks)
