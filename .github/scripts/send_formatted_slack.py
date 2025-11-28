import os
import json
import requests
import re

# 환경 변수 가져오기
webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
file_path = os.environ.get('FILE_PATH') # 내용 대신 경로를 받음

if not webhook_url or not file_path:
    print("Error: 필수 환경 변수(WEBHOOK_URL 또는 FILE_PATH)가 없습니다.")
    exit(1)

# Python이 직접 파일 읽기 (이게 훨씬 안전함)
try:
    with open(file_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
except FileNotFoundError:
    print(f"Error: 파일을 찾을 수 없습니다 -> {file_path}")
    exit(1)

blocks = []
blocks.append({
    "type": "header",
    "text": {"type": "plain_text", "text": "📰 오늘의 뉴스레터가 도착했습니다!", "emoji": True}
})

lines = md_content.split('\n')
for line in lines:
    line = line.strip()
    if not line: continue
        
    # 이미지 링크 찾기
    img_match = re.search(r'!\[.*?\]\((.*?)\)', line)
    
    if img_match:
        blocks.append({
            "type": "image",
            "image_url": img_match.group(1),
            "alt_text": "News Image"
        })
    elif line.startswith('##'):
        text = line.replace('#', '').strip()
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{text}*"}
        })
    else:
        # 텍스트가 너무 길면 잘릴 수 있으므로 3000자 제한 안전장치
        if len(line) > 3000:
            line = line[:2997] + "..."
            
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": line}
        })

# 블록이 비어있지 않을 때만 전송
if len(blocks) > 1:
    payload = {"blocks": blocks}
    response = requests.post(
        webhook_url, 
        data=json.dumps(payload), 
        headers={'Content-Type': 'application/json'}
    )
    print(f"Status Code: {response.status_code}")
    print(response.text)
else:
    print("보낼 내용이 없습니다.")
