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
    return text

def flush_text_buffer():
    """
    현재까지 쌓인 텍스트 버퍼를 슬랙 블록으로 변환하여 추가.
    텍스트가 3000자를 넘을 경우에만 '줄바꿈' 단위로 안전하게 나눔.
    """
    global current_text_buffer, blocks
    
    text = current_text_buffer.strip()
    if not text:
        return

    # 슬랙 제한(3000자) 대비 안전하게 2500자로 설정
    LIMIT = 2500
    
    # 1. 텍스트가 안전 범위 내라면 그냥 추가
    if len(text) <= LIMIT:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": text}
        })
    # 2. 텍스트가 너무 길면 '줄바꿈' 기준으로 쪼개서 추가
    else:
        while len(text) > LIMIT:
            # 제한 길이 근처에서 가장 마지막 줄바꿈(\n) 위치를 찾음
            split_index = text.rfind('\n', 0, LIMIT)
            
            # 줄바꿈이 없으면(엄청 긴 한 문장) 어쩔 수 없이 LIMIT에서 자름
            if split_index == -1:
                split_index = LIMIT
                
            chunk = text[:split_index]
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": chunk}
            })
            # 남은 텍스트로 계속 루프
            text = text[split_index:].strip()
        
        # 남은 자투리 추가
        if text:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": text}
            })
            
    # 버퍼 초기화
    current_text_buffer = ""

# --- 메인 로직 ---

# 1. 메인 헤더 추가 (가장 위)
blocks.append({
    "type": "header",
    "text": {"type": "plain_text", "text": main_header, "emoji": True}
})
blocks.append({"type": "divider"})

lines = md_content.split('\n')

for line in lines:
    line = line.strip()
    
    # [기준 1] 이미지 발견 (![alt](url))
    # 이미지는 새로운 뉴스 아이템의 '시각적 시작'이므로, 이전 텍스트를 모두 털어내고 이미지를 배치함.
    img_match = re.search(r'!\[.*?\]\((.*?)\)', line)
    
    if img_match:
        flush_text_buffer() # 이전 텍스트 블록 생성
        
        image_url = img_match.group(1)
        # URL 유효성 체크
        if image_url and image_url.startswith('http'):
            blocks.append({
                "type": "image",
                "image_url": image_url,
                "alt_text": "News Image"
            })
            
    # [기준 2] 구분선 (---)
    # 뉴스 아이템의 '논리적 종료'이므로, 텍스트를 털어내고 구분선을 그음.
    elif line == '---':
        flush_text_buffer()
        blocks.append({"type": "divider"})
        
    # [기준 3] 제목 (##)
    # 제목은 텍스트 버퍼의 시작점이 됨. (강제로 굵게 처리)
    elif line.startswith('##'):
        # 혹시 이미지가 없고 제목만 있는 경우를 대비해 flush 한 번 수행
        # (이미지 뒤에 바로 제목이 오면 buffer가 비어있으니 영향 없음)
        if current_text_buffer: 
             flush_text_buffer()

        clean_line = clean_markdown(line.replace('#', '').strip())
        current_text_buffer += f"*{clean_line}*\n"
        
    # 일반 텍스트 -> 버퍼에 계속 쌓음
    elif line:
        current_text_buffer += clean_markdown(line) + "\n"

# 루프 종료 후 남은 텍스트 처리
flush_text_buffer()

# --- 전송하기 ---

# 슬랙 블록 개수 제한 (50개) 안전장치
# 뉴스가 너무 많으면 50개까지만 잘라서 보냄 (안 그러면 아예 전송 실패함)
final_blocks = blocks[:50]
payload = {"blocks": final_blocks}

print(f"🚀 Sending file: {file_path} (Blocks: {len(final_blocks)})")

try:
    response = requests.post(
        webhook_url, 
        data=json.dumps(payload), 
        headers={'Content-Type': 'application/json'}
    )
    
    # 성공 여부 출력
    if response.status_code == 200:
        print("✅ Slack Message Sent Successfully!")
    else:
        print(f"❌ Slack Error: {response.text}")
        
except Exception as e:
    print(f"❌ Script Error: {str(e)}")
