 너무 길어 잘렸습니다)"; exit; } if (total_len + item_len > limit) { exit; } print; total_len += item_len; }' "$FILEPATH")

  # 3. 마크다운 -> 슬랙 변환 (sed)
  # - 이미지 태그 제거 및 링크화
  CONTENT=$(echo "$CONTENT" | sed -E 's/!\[([^]]*)\]\(([^)]+)\)/<\2|📷 이미지 보기>/g')
  # - 링크 변환
  CONTENT=$(echo "$CONTENT" | sed -E 's/\[([^]]+)\]\(([^)]+)\)/<\2|\1>/g')
  # - 굵은 글씨 변환
  CONTENT=$(echo "$CONTENT" | sed -E 's/\*\*([^*]+)\*\*/*\1*/g')
  # - 헤더 변환
  CONTENT=$(echo "$CONTENT" | sed -E 's/^#{1,6}\s+(.*)/*\1*/g')

  # 4. JSON 생성 (jq 사용 - 가장 안전함)
  # jq는 설치 없이 ubuntu-latest에서 바로 사용 가능합니다.
  JSON_PAYLOAD=$(jq -n \
    --arg header "$MSG_HEADER" \
    --arg content "$CONTENT" \
    '{
      text: $header,
      blocks: [
        {
          type: "header",
          text: { type: "plain_te#!/bin/bash
set -e

TODAY_KST=$(TZ="Asia/Seoul" date '+%-m월 %-d일')

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
  CONTENT=$(awk 'BEGIN{RS="---"; ORS="---"; total_len=0; limit=2800} { item_len = length($0 ORS); if (NR == 1 && item_len > limit) { print substr($0, 1, limit) "...(항목이xt", text: ("📰 " + $header) }
        },
        { type: "divider" },
        {
          type: "section",
          text: { type: "mrkdwn", text: $content }
        }
      ]
    }')

  # 5. 전송
  curl --fail -X POST -H 'Content-type: application/json' \
    --data "$JSON_PAYLOAD" \
    "$SLACK_WEBHOOK_URL"
  
  echo "Sent message for $FILEPATH"
done
