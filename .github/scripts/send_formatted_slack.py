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
# 오류 안내문이 그대로 커밋됨. 그런 파일은 본문 대신 짧은 알림만 전송한다.
BROKEN_OPENINGS = [
    "죄송", "안녕하세요", "안내드립니다", "요청하신", "요청해주신",
    "요청 감사", "이미 여러", "알려주",
]

def is_broken_report(content):
    # LLM의 사과/되묻기 문구로 시작하면 깨진 리포트로 판단
    head = content.lstrip()[:30]
    if any(p in head for p in BROKEN_OPENINGS):
        return True
    # 정상 리포트는 항상 기사/논문 링크나 이미지를 포함함 (깨진 리포트는 전부 0개)
    return len(re.findall(r'\]\(http', content)) == 0

# 깨진 리포트는 채널에 아무것도 보내지 않고 조용히 건너뜀 (로그로만 남김)
if is_broken_report(md_content):
    print(f"⚠️ 깨진 리포트 감지({category}), Slack 전송 안 함 -> {file_path}")
    exit(0)

# --- 마크다운 → Slack 블록 변환 ---

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

def clean_markdown(text):
    text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)  # 굵게
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<\2|\1>', text)  # 링크
    text = text.replace("**", "")
    return text

blocks = [
    {"type": "header", "text": {"type": "plain_text", "text": main_header, "emoji": True}},
    {"type": "divider"},
]
current_text_buffer = ""
bold_next_line = False  # "## 제목:" 처럼 제목이 다음 줄에 오는 경우

def flush_text_buffer():
    global current_text_buffer
    text = current_text_buffer.strip()
    current_text_buffer = ""
    if not text:
        return
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

for line in md_content.split('\n'):
    line = line.strip()

    # 리포트 뒤에 붙는 LLM 후속 안내문은 전송하지 않음
    if line.startswith("다음 단계 제안"):
        break
    # "(주의: 아래 요약은 abstract 기반 초안…" 같은 면책 문구 제거
    if line.startswith("(주의"):
        continue

    img_match = re.search(r'!\[(.*?)\]\((.*?)\)', line)

    if img_match:
        alt_text, url = img_match.group(1).strip(), img_match.group(2).strip()
        if is_usable_url(url) and is_image_url(url):
            flush_text_buffer()
            blocks.append({
                "type": "image",
                "image_url": url,
                "alt_text": alt_text or "News Image",
            })
        elif is_usable_url(url):
            # 이미지가 아닌 파일(예: arXiv PDF)은 텍스트 링크로
            label = alt_text or "파일 보기"
            current_text_buffer += f"📄 <{url}|{label}>\n"
        # 잘린/깨진 URL은 표시할 방법이 없으므로 조용히 버림

    elif line.startswith('![') or line.startswith('https://scontent'):
        # 닫는 괄호조차 없이 잘린 이미지 마크다운 → 버림 (생마크다운 노출 방지)
        continue

    elif line == '---':
        flush_text_buffer()
        blocks.append({"type": "divider"})

    elif line.startswith('##'):
        flush_text_buffer()
        heading = clean_markdown(line.lstrip('#').strip())
        # "제목: X" 헤딩은 접두어를 떼고 제목만 강조
        if heading.startswith('제목:'):
            heading = heading[len('제목:'):].strip()
        if heading:
            current_text_buffer += f"*{heading}*\n"
        else:
            bold_next_line = True

    elif line:
        cleaned = clean_markdown(line)
        if cleaned:
            if bold_next_line:
                cleaned = f"*{cleaned}*"
                bold_next_line = False
            current_text_buffer += cleaned + "\n"

flush_text_buffer()

# upstream이 파일을 중간에서 잘라먹으면 마지막 항목이 제목만 남는 경우가 있음.
# 끝에 매달린 구분선/이미지/제목만 있는 섹션은 잘라냄.
def is_dangling(block):
    if block["type"] in ("divider", "image"):
        return True
    if block["type"] == "section":
        return re.fullmatch(r'\*[^\n*]+\*', block["text"]["text"].strip()) is not None
    return False

while len(blocks) > 2 and is_dangling(blocks[-1]):
    blocks.pop()

if len(blocks) <= 2:
    print(f"⚠️ 전송할 본문이 없습니다({category}), Slack 전송 안 함 -> {file_path}")
    exit(0)

print(f"🚀 Sending file: {file_path} (Blocks: {len(blocks)})")
send_blocks(blocks)
