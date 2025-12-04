import os
import json
import requests
import re

# --- 환경 변수 가져오기 ---
webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
file_path = os.environ.get('FILE_PATH')

if not webhook_url or not file_path:
    print("Error: 필수 환경 변수(SLACK_WEBHOOK_URL, FILE_PATH)가 없습니다.")
    exit(1)

# --- 카테고리별 헤더 설정 ---
if "논문" in file_path:
    main_header = "📚 오늘의 논문 요약이 도착했습니다!"
elif "프로덕트" in file_path:
    main_header = "🚀 오늘의 프로덕트 뉴스가 도착했습니다!"
else:
    main_header = "📰 오늘의 뉴스레터가 도착했습니다!"

# --- 파일 읽기 ---
try:
    with open(file_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
except FileNotFoundError:
    print(f"Error: 파일을 찾을 수 없습니다 -> {file_path}")
    exit(1)

blocks = []
current_text_buffer = ""

# --- 헬퍼 함수들 ---

def clean_markdown(text):
    """마크다운 문법을 슬랙용으로 변환"""
    text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text) # 굵게
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<\2|\1>', text) # 링크
    text = text.replace("**", "") # 빈 볼드 제거
    return text

def is_valid_image_url(url):
    """URL이 진짜 이미지 파일인지 확장자로 검사"""
    if not url or not url.startswith('http'):
        return False
    # 이미지 확장자 리스트 (소문자로 변환 후 비교)
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    return any(url.lower().endswith(ext) for ext in valid_extensions)

def flush_text_buffer():
    """텍스트 버퍼를 블록으로 변환"""
    global current_text_buffer, blocks
    
    text = current_text_buffer.strip()
    if not text:
        current_text_buffer = ""
        return

    LIMIT = 2900
    
    if len(text) <= LIMIT:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": text}
        })
    else:
        while len(text) > LIMIT:
            split_index = text.rfind('\n', 0, LIMIT)
            if split_index == -1:
                split_index = LIMIT
                
            chunk = text[:split_index].strip()
            if chunk:
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": chunk}
                })
            text = text[split_index:].strip()
        
        if text:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": text}
            })
            
    current_text_buffer = ""

# --- 메인 로직 ---

blocks.append({
    "type": "header",
    "text": {"type": "plain_text", "text": main_header, "emoji": True}
})
blocks.append({"type": "divider"})

lines = md_content.split('\n')

for line in lines:
    line = line.strip()
    
    # 1. 이미지 패턴 발견 (![...](URL))
    img_match = re.search(r'!\[.*?\]\((.*?)\)', line)
    
    if img_match:
        image_url = img_match.group(1)
        
        # [핵심 수정] 진짜 이미지(.jpg, .png 등)일 때만 이미지 블록으로 만듦
        if is_valid_image_url(image_url):
            flush_text_buffer()
            blocks.append({
                "type": "image",
                "image_url": image_url,
                "alt_text": "News Image"
            })
        else:
            # 이미지가 아니면(예: PDF 링크) 그냥 텍스트 링크로 변환해서 본문에 붙임
            # 예: <https://arxiv.org/pdf/...|PDF 다운로드>
            current_text_buffer += f"\n📄 <{image_url}|파일 보기>\n"
            
    # 2. 구분선
    elif line == '---':
        flush_text_buffer()
        blocks.append({"type": "divider"})
        
    # 3. 제목
    elif line.startswith('##'):
        if current_text_buffer: 
             flush_text_buffer()
        clean_line = clean_markdown(line.replace('#', '').strip())
        if clean_line:
            current_text_buffer += f"*{clean_line}*\n"
        
    # 4. 일반 텍스트
    elif line:
        cleaned = clean_markdown(line)
        if cleaned:
            current_text_buffer += cleaned + "\n"

flush_text_buffer()

# --- 전송하기 ---

final_blocks = blocks[:50]
payload = {"blocks": final_blocks}

print(f"🚀 Sending file: {file_path} (Blocks: {len(final_blocks)})")

try:
    response = requests.post(
        webhook_url, 
        data=json.dumps(payload), 
        headers={'Content-Type': 'application/json'}
    )
    
    if response.status_code == 200:
        print("✅ Slack Message Sent Successfully!")
    else:
        print(f"❌ Slack Error: {response.text}")
        print("--- Sent Payload (Debugging) ---")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        
except Exception as e:
    print(f"❌ Script Error: {str(e)}")
