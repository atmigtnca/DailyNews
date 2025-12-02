import os
import json
import requests
import re

# 환경 변수 확인
webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
file_path = os.environ.get('FILE_PATH')

if not webhook_url or not file_path:
    print("Error: 필수 환경 변수가 없습니다.")
    exit(1)

# 1. 카테고리(폴더명)에 따른 제목과 이모지 설정
if "논문" in file_path:
    header_text = "📚 오늘의 논문 요약이 도착했습니다!"
    color = "#36a64f" # 초록색
elif "프로덕트" in file_path:
    header_text = "🚀 오늘의 프로덕트 뉴스가 도착했습니다!"
    color = "#e01e5a" # 빨간색
else:
    header_text = "📰 오늘의 뉴스레터가 도착했습니다!"
    color = "#ecb22e" # 노란색

# 파일 읽기
try:
    with open(file_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
except FileNotFoundError:
    print(f"Error: 파일을 찾을 수 없습니다 -> {file_path}")
    exit(1)

# 2. Slack 전송용 블록 조립
blocks = []

# (1) 헤더 추가
blocks.append({
    "type": "header",
    "text": {
        "type": "plain_text",
        "text": header_text,
        "emoji": True
    }
})
blocks.append({"type": "divider"})

# (2) 본문 파싱 및 변환
lines = md_content.split('\n')
current_text_chunk = ""

def clean_markdown(text):
    """마크다운을 슬랙 포맷으로 변환"""
    # 굵게: **text** -> *text*
    text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
    # 링크: [text](url) -> <url|text>
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<\2|\1>', text)
    return text

for line in lines:
    line = line.strip()
    
    # 이미지 발견 시 (![alt](url))
    img_match = re.search(r'!\[.*?\]\((.*?)\)', line)
    
    if img_match:
        # 쌓인 텍스트가 있으면 먼저 블록으로 추가
        if current_text_chunk:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": current_text_chunk}
            })
            current_text_chunk = ""
            
        # 이미지 블록 추가
        image_url = img_match.group(1)
        # 이미지 URL이 유효한지 체크 (http로 시작하는지)
        if image_url.startswith('http'):
            blocks.append({
                "type": "image",
                "image_url": image_url,
                "alt_text": "Image"
            })
    
    # 구분선 (---)
    elif line == '---':
        if current_text_chunk:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": current_text_chunk}
            })
            current_text_chunk = ""
        blocks.append({"type": "divider"})
        
    # 헤더 (## 제목)
    elif line.startswith('##'):
        # 헤더도 텍스트 덩어리에 포함시키되 굵게 처리
        clean_line = clean_markdown(line.replace('#', '').strip())
        current_text_chunk += f"\n*{clean_line}*\n"
        
    # 일반 텍스트
    elif line:
        current_text_chunk += clean_markdown(line) + "\n"

# 마지막 남은 텍스트 추가
if current_text_chunk:
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": current_text_chunk}
    })

# 3. 전송 (블록 개수 제한 고려하여 분할 전송하거나 50개까지만)
payload = {"blocks": blocks[:50]} # 슬랙은 한 번에 최대 50개 블록만 허용

print(f"Sending file: {file_path}")
response = requests.post(
    webhook_url, 
    data=json.dumps(payload), 
    headers={'Content-Type': 'application/json'}
)

print(f"Slack Response: {response.text}")
