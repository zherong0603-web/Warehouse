#!/bin/zsh
set -u

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

SCRIPT_PATH="${0:A}"
PACKAGE_DIR="${SCRIPT_PATH:h}"
CONFIG_PATH="${OPC_LAUNCHER_CONFIG:-$PACKAGE_DIR/config.json}"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
DESKTOP_LAUNCHER="$HOME/Desktop/OPC开工.command"

dialog() {
  local message="$1"
  /usr/bin/osascript -e "display dialog \"${message//\"/\\\"}\" with title \"OPC工位卸载器\" buttons {\"知道了\"} default button \"知道了\"" >/dev/null 2>&1 || true
}

if [[ -x "$PYTHON_BIN" && -f "$CONFIG_PATH" ]]; then
  WORKSPACE_ROOT="$("$PYTHON_BIN" - "$CONFIG_PATH" <<'PY'
import json, os, pathlib, sys
config = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(pathlib.Path(os.path.expanduser(config.get("workspaceRoot", "~/AI工位/OPC小红书封面工具"))).resolve())
PY
)"
else
  WORKSPACE_ROOT="$HOME/AI工位/OPC小红书封面工具"
fi

INSTALL_DIR="$WORKSPACE_ROOT/00_入口/OPC工位启动器V0.2"

if [[ -f "$DESKTOP_LAUNCHER" ]] && /usr/bin/grep -q "OPC工位启动器V0.2" "$DESKTOP_LAUNCHER"; then
  /bin/rm -f "$DESKTOP_LAUNCHER"
fi

if [[ -d "$INSTALL_DIR" ]]; then
  /bin/rm -rf "$INSTALL_DIR"
fi

if [[ "${DELETE_OPC_CHROME_PROFILE:-0}" == "1" ]]; then
  /bin/rm -rf "$WORKSPACE_ROOT/00_入口/.chrome-profile"
fi

dialog "卸载完成。\n\n已删除桌面入口和启动器程序。\n\n项目资料文件夹仍保留在：\n$WORKSPACE_ROOT\n\n如需删除隔离 Chrome 登录资料，可让 Ryan 处理，或设置 DELETE_OPC_CHROME_PROFILE=1 后再运行。"
echo "Uninstalled OPC launcher. Workspace data kept: $WORKSPACE_ROOT"
