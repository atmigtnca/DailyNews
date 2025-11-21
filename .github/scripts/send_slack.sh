#!/bin/bash
set -e

# 오늘 날짜 (KST)
TODAY_KST=$(TZ="Asia/Seoul" date '+%-m월 %-d일')

# 파일 목록을 줄 단위로 읽어서 반복
echo "$FILE_LIST" | while IFS= read -r FILEPATH; do
  if [ -z "$FILEPATH" ]; then
    continue
  fi

  echo "Processing file: $FILEPATH"

  # 1. 헤더 설정
  MSG_HEADER=""
  if [[ "$FILEPATH" == 뉴스레터* ]]; then
    MSG_HEADER="$TODAY_KST 오늘의 뉴스레터가 도착했습니다! 🚀"
  elif [[ "$FILEPATH" == 프로덕트* ]]; then
    MSG_HEADER="$TODAY_KST 오늘의 프로덕트가 도착했습니다! 🚀"
  elif [[ "$FILEPATH" == 논문* ]]; then
    MSG_HEADER="$TODAY_KST 오늘의 논문이 도착했습니다! 🚀"
  else
    MSG_HEADER="$TODAY_KST 새 소식($FILEPATH)이 도착했습니다! 🚀"
  fi

  # 2. 내용 읽기 및 스마트 자르기 (awk)
  # '---' 구분자를 기준으로 항목을 더하다가 2800자를 넘으면 멈춤
  CONTENT=$(awk '
    BEGIN { RS="---"; ORS="---"; total_len=0; limit=2800 }
    {
      item_len = length($0) + length(ORS);
      # 첫 번째 항목부터 너무 길면 잘라서 출력 후 종료
      if (NR == 1 && item_len > limit) {
        print substr($0, 1, limit) "\n...(내용이 너무 길어 잘렸습니다)";
        exit;
      }
      # 제한을 넘기면 종료
      if (total_len + item_len > limit) {
        exit;
      }
      print $0;
      total_len += item_len;
    }
  ' "$FILEPATH")

  # 3. 마크다운 -> 슬랙 형식 변환 (sed)
  # 이미지: ![alt](url) -> <url|📷 이미지 보기>
  CONTENT=$(echo "$CONTENT" | sed -E 's/!\[([^]]*)\]\(([^)]+)\)/<\2|📷 이미지 보기>/g')
  # 링크: [text](url) -> <url|text>
  CONTENT=$(echo "$CONTENT" | sed -E 's/\[([^]]+)\]\(([^)]+)\)/<\2|\1>/g')
  # 굵게: **text** -> *text*
  CONTENT=$(echo "$CONTENT" | sed -E 's/\*\*([^*]+)\*\*/*\1*/g')
  # 헤더: ## 제목 -> *제목*
  CONTENT=$(echo "$CONTENT" | sed -E 's/^#{1,6}\s+(.*)/*\1*/g')

  # 4. JSON 생성 (jq 사용)
  JSON_PAYLOAD=$(jq -n \
    --arg header "$MSG_HEADER" \
    --arg content "$CONTENT" \
    '{
      text: $header,
      blocks: [
        {
          type: "header",
          text: { type: "plain_text", text: ("📰 " + $header) }
        },
        { type: "divider" },
        {
          type: "section",
          text: { type: "mrkdwn", text: $content }
        }
      ]
    }')

  # 5. 슬랙 전송
  curl --fail -X POST -H 'Content-type: application/json' \
    --data "$JSON_PAYLOAD" \
    "$SLACK_WEBHOOK_URL"

  echo "Sent message for $FILEPATH"

done
