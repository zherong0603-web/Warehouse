#!/bin/zsh
set -u

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

SCRIPT_PATH="${0:A}"
PACKAGE_DIR="${SCRIPT_PATH:h}"
CONFIG_PATH="$PACKAGE_DIR/config.json"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"

fail() {
  local message="$1"
  echo "$message" >&2
  /usr/bin/osascript -e "display dialog \"${message//\"/\\\"}\" with title \"OPC工位安装失败\" buttons {\"知道了\"} default button \"知道了\" with icon caution" >/dev/null 2>&1 || true
  exit 2
}

info_dialog() {
  local message="$1"
  /usr/bin/osascript -e "display dialog \"${message//\"/\\\"}\" with title \"OPC工位安装器\" buttons {\"知道了\"} default button \"知道了\"" >/dev/null 2>&1 || true
}

if [[ ! -x "$PYTHON_BIN" ]]; then
  fail "未找到 /usr/bin/python3，无法读取配置。请把这个提示发给 Ryan。"
fi

if [[ ! -f "$CONFIG_PATH" ]]; then
  fail "找不到 config.json，请确认 install.command 和 config.json 在同一个文件夹。"
fi

WORKSPACE_ROOT="$("$PYTHON_BIN" - "$CONFIG_PATH" <<'PY'
import json, os, pathlib, sys
config = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(pathlib.Path(os.path.expanduser(config.get("workspaceRoot", "~/AI工位/OPC小红书封面工具"))).resolve())
PY
)"

INSTALL_DIR="$WORKSPACE_ROOT/00_入口/OPC工位启动器V0.2"
DESKTOP_LAUNCHER="$HOME/Desktop/OPC开工.command"

find_aerospace() {
  command -v aerospace >/dev/null 2>&1 && return 0
  [[ -x /opt/homebrew/bin/aerospace ]] && return 0
  [[ -x /usr/local/bin/aerospace ]] && return 0
  return 1
}

if ! find_aerospace; then
  if command -v brew >/dev/null 2>&1; then
    CHOICE="$(/usr/bin/osascript -e 'button returned of (display dialog "OPC 工位需要免费组件 AeroSpace 来保证独立工作区。是否现在用 Homebrew 安装？" with title "需要安装 AeroSpace" buttons {"取消", "安装"} default button "安装" with icon caution)' 2>/dev/null || true)"
    if [[ "$CHOICE" != "安装" ]]; then
      fail "已取消安装。没有 AeroSpace 时，OPC开工.command 会安全失败，不会打开项目窗口。"
    fi
    brew install --cask nikitabobko/tap/aerospace || fail "AeroSpace 安装失败。请把终端里的错误发给 Ryan。"
  else
    fail "未检测到 AeroSpace，也未检测到 Homebrew。为避免污染当前桌面，安装已停止。请把这个提示发给 Ryan 处理。"
  fi
fi

/bin/mkdir -p "$INSTALL_DIR" || fail "无法创建安装目录：$INSTALL_DIR"
/bin/cp -f "$PACKAGE_DIR/OPC开工.command" "$INSTALL_DIR/OPC开工.command" || fail "复制 OPC开工.command 失败。"
/bin/cp -f "$PACKAGE_DIR/config.json" "$INSTALL_DIR/config.json" || fail "复制 config.json 失败。"
/bin/cp -f "$PACKAGE_DIR/README_小白使用说明.md" "$INSTALL_DIR/README_小白使用说明.md" 2>/dev/null || true
/bin/cp -f "$PACKAGE_DIR/技术说明.md" "$INSTALL_DIR/技术说明.md" 2>/dev/null || true
/bin/cp -f "$PACKAGE_DIR/uninstall.command" "$INSTALL_DIR/uninstall.command" || fail "复制 uninstall.command 失败。"
/bin/chmod +x "$INSTALL_DIR/OPC开工.command" "$INSTALL_DIR/uninstall.command"

"$INSTALL_DIR/OPC开工.command" --prepare-only || fail "准备 OPC 工位文件夹失败。"

/bin/cat >"$DESKTOP_LAUNCHER" <<EOF
#!/bin/zsh
export OPC_LAUNCHER_CONFIG="$INSTALL_DIR/config.json"
exec "$INSTALL_DIR/OPC开工.command" "\$@"
EOF
/bin/chmod +x "$DESKTOP_LAUNCHER" || fail "无法设置桌面入口权限：$DESKTOP_LAUNCHER"

/usr/bin/open -g -a AeroSpace >/dev/null 2>&1 || true

info_dialog "安装完成。\n\n以后只需要双击桌面的 OPC开工.command。\n\n如果 AeroSpace 第一次启动时要求辅助功能权限，请按系统提示允许；未授权时启动器会安全失败，不会打开项目窗口。"
echo "Installed OPC launcher to: $INSTALL_DIR"
echo "Desktop launcher: $DESKTOP_LAUNCHER"
