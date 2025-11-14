#!/bin/bash
# Exit immediately if any command fails
set -e

# Get today's date
TODAY_KST=$(TZ="Asia/Seoul" date '+%-m월 %-d일')

# Loop over each line in the FILE_LIST (passed from env)
while IFS= read -r FILEPATH; do
  if [ -z "$FILEPATH" ]; then
    continue # Skip empty lines
  fi

  echo "Processing file: $FILEPATH"
  
  # --- 3a. Set Custom Slack Message ---
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

  # --- 3b. Dynamically Read & Truncate Content ---
  content=$(awk 'BEGIN{RS="---"; ORS="---"; total_len=0; limit=2800} { item_len = length($0 ORS); if (NR == 1 && item_len > limit) { print substr($0, 1, limit) "...(항목이 너무 길어 잘렸습니다)"; exit; } if (total_len + item_len > limit) { exit; } print; total_len += item_len; }' "$FILEPATH")

  # --- 3c. Escape for JSON ---
  content="${content//\\/\\\\}"
  content="${content//\"/\\\"}"
  content="${content//$'\n'/\\n}"
  content="${content//$'\r'/\\r}"

  # --- 3d. Send to Slack (using curl) ---
  # 'cat <<-EOF' is used for clean multiline string
  SLACK_JSON=$(cat <<-EOF
  {
    "text": "$MSG_HEADER",
    "blocks": [
      {
        "type": "header",
        "text": { "type": "plain_text", "text": "📰 $MSG_HEADER" }
      },
      { "type": "divider" },
      {
        "type": "section",
        "text": { "type": "mrkdwn", "text": "$content" }
      }
    ]
  }
EOF
  )

  # (OK) curl command with --fail
  # The Webhook URL is now read from the environment variable
  curl --fail -X POST -H 'Content-type: application/json' --data "$SLACK_JSON" "$SLACK_WEBHOOK_URL"
  
  echo "Sent message for $FILEPATH"
  
done <<< "$FILE_LIST"
