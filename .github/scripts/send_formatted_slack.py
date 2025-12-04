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
    # 굵게: **text** -> *text*
    text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
    # 링크: [text](url) -> <url|text>
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<\2|\1>', text)
    # 슬랙에서 금지된 빈 볼드체(**) 제거
    text = text.replace("**", "")
    return text

def flush_text_buffer():
    """텍스트 버퍼를 블록으로 변환 (빈 블록 방지 로직 포함)"""
    global current_text_buffer, blocks
    
    # 공백 제거 후 확인
    text = current_text_buffer.strip()
    if not text:
        current_text_buffer = ""
        return

    LIMIT = 2900  # 슬랙 제한 3000자 안전 마진
    
    if len(text) <= LIMIT:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": text}
        })
    else:
        # 긴 텍스트 분할 처리
        while len(text) > LIMIT:
            split_index = text.rfind('\n', 0, LIMIT)
            if split_index == -1:
                split_index = LIMIT
                
            chunk = text[:split_index].strip()
            # 분할된 조각이 비어있지 않을 때만 추가
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
    
    # 1. 이미지 발견
    img_match = re.search(r'!\[.*?\]\((.*?)\)', line)
    
    if img_match:
        flush_text_buffer()
        image_url = img_match.group(1)
        
        # [중요] 이미지 URL 유효성 검사 (http로 시작하고, 빈 값이 아닐 때만)
        if image_url and image_url.startswith('http') and len(image_url) > 5:
            blocks.append({
                "type": "image",
                "image_url": image_url,
                "alt_text": "News Image"
            })
        else:
            # 이미지가 깨졌거나 로컬 경로면 링크 텍스트로 대체 (에러 방지)
            current_text_buffer += f" (이미지 링크: {image_url})\n"
            
    # 2. 구분선
    elif line == '---':
        flush_text_buffer()
        blocks.append({"type": "divider"})
        
    # 3. 제목
    elif line.startswith('##'):
        if current_text_buffer: 
             flush_text_buffer()
        clean_line = clean_markdown(line.replace('#', '').strip())
        if clean_line: # 제목이 비어있지 않을 때만
            current_text_buffer += f"*{clean_line}*\n"
        
    # 4. 일반 텍스트
    elif line:
        cleaned = clean_markdown(line)
        if cleaned: # 변환 후에도 내용이 있을 때만
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
        # [디버깅] 실패 시 어떤 블록이 문제인지 확인하기 위해 페이로드 출력
        print(f"❌ Slack Error: {response.text}")
        print("--- Sent Payload (Debugging) ---")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        
except Exception as e:
    print(f"❌ Script Error: {str(e)}")
