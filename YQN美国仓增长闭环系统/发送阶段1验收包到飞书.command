#!/bin/zsh

PROJECT_DIR="/Users/oldking/Documents/Codex/2026-06-22/zarazhangrui-skill-minimac-codex/work/feishu-codex-default/YQN美国仓增长闭环系统"
ZIP_PATH="08_验收包/YQN_US_Warehouse_Stage1_Acceptance_Pack_20260624_1639.zip"
CHAT_ID="oc_d89c45bb9a041dee17375620cf26fb1f"
LOG_PATH="$PROJECT_DIR/logs/send_acceptance_zip_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$PROJECT_DIR/logs"

{
  echo "send_acceptance_zip_start=$(date '+%Y-%m-%d %H:%M:%S')"
  cd "$PROJECT_DIR" || exit 1

  export PATH="/Users/oldking/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

  export LARK_CHANNEL="1"
  export LARK_CHANNEL_HOME="/Users/oldking/.lark-channel"
  export LARK_CHANNEL_PROFILE="codex"
  export LARK_CHANNEL_CONFIG="/Users/oldking/.lark-channel/profiles/codex/lark-cli-source/config.json"
  export LARKSUITE_CLI_CONFIG_DIR="/Users/oldking/.lark-channel/profiles/codex/lark-cli"

  export HTTP_PROXY="http://127.0.0.1:7897"
  export HTTPS_PROXY="http://127.0.0.1:7897"
  export ALL_PROXY="http://127.0.0.1:7897"
  export http_proxy="http://127.0.0.1:7897"
  export https_proxy="http://127.0.0.1:7897"
  export all_proxy="http://127.0.0.1:7897"
  export NO_PROXY=""
  export no_proxy=""

  echo "zip=$PROJECT_DIR/$ZIP_PATH"
  echo "chat_id=$CHAT_ID"
  echo "lark_cli=$(command -v lark-cli)"

  lark-cli im +messages-send --chat-id "$CHAT_ID" --file "$ZIP_PATH" --format json
  status=$?
  echo "exit_status=$status"
  if [ "$status" -eq 0 ]; then
    echo "SEND_RESULT=SUCCESS"
  else
    echo "SEND_RESULT=FAILED"
  fi
  echo "send_acceptance_zip_end=$(date '+%Y-%m-%d %H:%M:%S')"
} 2>&1 | tee "$LOG_PATH"
