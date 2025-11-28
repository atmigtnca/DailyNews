# .github/scripts/send_formatted_slack.py
import os
import json
import requests
import re

# 환경 변수에서 값 가져오기
webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
md_content = os.environ.get('NEWSLETTER_CONTENT')

if not webhook_url or not md_content:
    print("Error: 환경 변수가 누락되었습니다.")
    exit(1)

blocks = []
# 뉴스레터 제목 추가
blocks.append({
    "type": "header",
    "text": {
        "type": "plain_text",
        "text": "📰 오늘의 뉴스레터가 도착했습니다!",
        "emoji": True
    }
})

# 본문 줄바꿈 기준으로 나누기
lines = md_content.split('\n')

for line in lines:
    line = line.strip()
    if not line:
        continue
        
    # 이미지 패턴 찾기: ![설명](URL)
    img_match = re.search(r'!\[.*?\]\((.*?)\)', line)
    
    if img_match:
        # 이미지가 있으면 '이미지 블록'으로 추가
        image_url = img_match.group(1)
        blocks.append({
            "type": "image",
            "image_url": image_url,
            "alt_text": "뉴스 이미지"
        })
    elif line.startswith('##'):
        # 제목(##)이면 굵게 표시
        text = line.replace('#', '').strip()
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{text}*"
            }
        })
    else:
        # 일반 텍스트
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": line
            }
        })

# 슬랙으로 전송
payload = {"blocks": blocks}
response = requests.post(
    webhook_url, 
    data=json.dumps(payload), 
    headers={'Content-Type': 'application/json'}
)

print(f"Status Code: {response.status_code}")
print(response.text)
