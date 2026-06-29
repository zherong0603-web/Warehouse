#!/bin/zsh
set -u

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

SCRIPT_PATH="${0:A}"
SCRIPT_DIR="${SCRIPT_PATH:h}"
CONFIG_PATH="${OPC_LAUNCHER_CONFIG:-$SCRIPT_DIR/config.json}"

if [[ ! -f "$CONFIG_PATH" ]]; then
  FALLBACK_CONFIG="$HOME/AI工位/OPC小红书封面工具/00_入口/OPC工位启动器V0.2/config.json"
  if [[ -f "$FALLBACK_CONFIG" ]]; then
    CONFIG_PATH="$FALLBACK_CONFIG"
  fi
fi

PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  /usr/bin/osascript -e 'display dialog "未找到 /usr/bin/python3，OPC 工位启动器已停止。请把这个提示发给 Ryan 处理；没有打开任何项目窗口。" buttons {"知道了"} default button "知道了" with icon caution' >/dev/null 2>&1 || true
  exit 2
fi

if [[ "${OPC_LAUNCHER_FOREGROUND:-0}" != "1" && "$#" -eq 0 ]]; then
  LOG_DIR="$HOME/Library/Logs/OPCLauncher"
  /bin/mkdir -p "$LOG_DIR"
  TERMINAL_WINDOW_ID="$(/usr/bin/osascript -e 'tell application "Terminal" to if (count of windows) > 0 then id of front window' 2>/dev/null || true)"
  OPC_LAUNCHER_FOREGROUND=1 OPC_LAUNCHER_TERMINAL_WINDOW_ID="$TERMINAL_WINDOW_ID" /usr/bin/nohup "$SCRIPT_PATH" --from-background >"$LOG_DIR/OPC开工.log" 2>&1 &
  if [[ -n "$TERMINAL_WINDOW_ID" ]]; then
    (
      /bin/sleep 0.8
      /usr/bin/osascript -e "tell application \"Terminal\" to if exists (first window whose id is $TERMINAL_WINDOW_ID) then close (first window whose id is $TERMINAL_WINDOW_ID)" >/dev/null 2>&1 || true
    ) &
  fi
  exit 0
fi

"$PYTHON_BIN" - "$CONFIG_PATH" "$SCRIPT_DIR" "$@" <<'PY'
import datetime as _dt
import html
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import time
import urllib.parse

APP_TITLE = "OPC工位启动器 V0.2"
NO_DIALOG = os.environ.get("OPC_LAUNCHER_NO_DIALOG") == "1"
DEFAULT_FOLDERS = [
    "00_入口",
    "01_商品资料_链接截图",
    "02_小红书参考案例",
    "03_封面素材",
    "04_Canva导出",
    "05_GPT输出文案",
    "06_最终成品",
    "07_Codex_未来开发",
    "08_归档",
]


def osa_quote(text):
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def run(cmd, timeout=15, check=False, capture=True):
    if capture:
        proc = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    else:
        proc = subprocess.run(cmd, timeout=timeout)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{shlex.join(cmd)}\n{getattr(proc, 'stderr', '')}".strip())
    return proc


def dialog(title, message, icon="caution"):
    if NO_DIALOG:
        return
    script = (
        f'display dialog {osa_quote(message)} '
        f'with title {osa_quote(title)} '
        f'buttons {{"知道了"}} default button "知道了" '
        f'with icon {icon}'
    )
    try:
        subprocess.run(["/usr/bin/osascript", "-e", script], timeout=20)
    except Exception:
        pass


def notify(message):
    if NO_DIALOG:
        return
    script = f'display notification {osa_quote(message)} with title {osa_quote(APP_TITLE)}'
    try:
        subprocess.run(["/usr/bin/osascript", "-e", script], timeout=8)
    except Exception:
        pass


def safe_fail(message, code=2):
    full = message + "\n\n已停止，未打开任何项目网页、Finder 或文档窗口。"
    print(f"[SAFE-FAIL] {full}", file=sys.stderr)
    dialog("未能进入独立项目工位", full)
    sys.exit(code)


def load_config(config_path):
    path = pathlib.Path(config_path).expanduser()
    if not path.exists():
        safe_fail(f"找不到配置文件：{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        safe_fail(f"配置文件不是有效 JSON：{path}\n{exc}")

    data.setdefault("projectName", "OPC小红书封面工具")
    data.setdefault("workspaceName", "OPC")
    data.setdefault("spaceBackend", "aerospace")
    data.setdefault("workspaceRoot", "~/AI工位/OPC小红书封面工具")
    data.setdefault("folders", DEFAULT_FOLDERS)
    data.setdefault("links", [])
    data.setdefault("chrome", {})

    if not isinstance(data["folders"], list) or not data["folders"]:
        safe_fail("config.json 里的 folders 必须是非空数组。")
    if not isinstance(data["links"], list):
        safe_fail("config.json 里的 links 必须是数组。")
    return data, path


def workspace_root(config):
    return pathlib.Path(os.path.expanduser(config["workspaceRoot"])).resolve()


def link_items(config):
    items = []
    for item in config.get("links", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        url = str(item.get("url", "")).strip()
        if name and url:
            items.append({"name": name, "url": url})
    chatgpt = str(config.get("chatgptUrl", "")).strip()
    if chatgpt and not any(x["url"] == chatgpt for x in items):
        items.insert(0, {"name": "ChatGPT OPC 项目对话", "url": chatgpt})
    return items


def folder_description(name):
    descriptions = {
        "00_入口": "工位首页、启动器、当天记录",
        "01_商品资料_链接截图": "商品链接、截图、原始信息",
        "02_小红书参考案例": "参考封面、标题、风格样例",
        "03_封面素材": "图片、Logo、字体、可复用素材",
        "04_Canva导出": "Canva 导出的中间版本",
        "05_GPT输出文案": "标题、卖点、封面文案",
        "06_最终成品": "最终可发布文件",
        "07_Codex_未来开发": "后续自动化和工具代码",
        "08_归档": "旧版本、历史资料",
    }
    return descriptions.get(name, "项目资料")


def file_url(path):
    return pathlib.Path(path).resolve().as_uri()


def prepare_workspace(config):
    root = workspace_root(config)
    root.mkdir(parents=True, exist_ok=True)
    for folder in config["folders"]:
        (root / folder).mkdir(parents=True, exist_ok=True)

    entry_dir = root / "00_入口"
    today = _dt.date.today().isoformat()
    record = entry_dir / f"今日开工记录_{today}.md"
    if not record.exists():
        record.write_text(
            "\n".join(
                [
                    f"# 今日开工记录 {today}",
                    "",
                    "- 开工目标：",
                    "- 今日要做：",
                    "- 需要补充的素材：",
                    "- 输出文件位置：06_最终成品",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    links = link_items(config)
    rows = []
    for folder in config["folders"]:
        path = root / folder
        rows.append(
            "<tr>"
            f"<td><a href=\"{html.escape(file_url(path))}\">{html.escape(folder)}</a></td>"
            f"<td>{html.escape(folder_description(folder))}</td>"
            "</tr>"
        )

    link_cards = []
    for item in links:
        link_cards.append(
            f"<a class=\"link-card\" href=\"{html.escape(item['url'], quote=True)}\">"
            f"<span>{html.escape(item['name'])}</span>"
            f"<small>{html.escape(item['url'])}</small>"
            "</a>"
        )

    project_name = config["projectName"]
    workspace_name = config.get("workspaceName", "OPC")
    home = entry_dir / "OPC工位首页.html"
    home.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(project_name)}工位首页</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1f2937;
      --muted: #64748b;
      --line: #d8dee8;
      --accent: #0f766e;
      --accent-2: #2563eb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.55;
    }}
    main {{
      width: min(1120px, calc(100vw - 40px));
      margin: 0 auto;
      padding: 32px 0 48px;
    }}
    header {{
      display: grid;
      gap: 8px;
      padding: 24px 0 18px;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{
      margin: 0;
      font-size: 32px;
      line-height: 1.18;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 0 0 14px;
      font-size: 20px;
      letter-spacing: 0;
    }}
    p {{ margin: 0; color: var(--muted); }}
    section {{
      margin-top: 26px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
    }}
    .link-card {{
      display: grid;
      gap: 6px;
      min-height: 92px;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      color: var(--text);
      text-decoration: none;
      background: #fbfcfe;
    }}
    .link-card:hover {{ border-color: var(--accent-2); }}
    .link-card span {{ font-weight: 700; }}
    .link-card small {{
      overflow-wrap: anywhere;
      color: var(--muted);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th, td {{
      padding: 10px 8px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{ color: var(--muted); font-weight: 600; }}
    a {{ color: var(--accent); }}
    .actions {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
      margin-top: 10px;
    }}
    .action {{
      padding: 12px 14px;
      border-left: 4px solid var(--accent);
      background: #f8fafc;
      border-radius: 6px;
    }}
    code {{
      padding: 2px 5px;
      background: #eef2f7;
      border-radius: 4px;
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{html.escape(project_name)}工位首页</h1>
      <p>工作区：{html.escape(workspace_name)} · 本地目录：<code>{html.escape(str(root))}</code></p>
    </header>

    <section>
      <h2>今日开工记录</h2>
      <p><a href="{html.escape(file_url(record))}">{html.escape(record.name)}</a></p>
      <div class="actions">
        <div class="action">先把商品链接、截图放进 <strong>01_商品资料_链接截图</strong></div>
        <div class="action">把参考图放进 <strong>02_小红书参考案例</strong></div>
        <div class="action">Canva 导出先放 <strong>04_Canva导出</strong>，定稿放 <strong>06_最终成品</strong></div>
      </div>
    </section>

    <section>
      <h2>常用链接</h2>
      <div class="grid">
        {''.join(link_cards) if link_cards else '<p>还没有配置链接，可以编辑 config.json 的 links。</p>'}
      </div>
    </section>

    <section>
      <h2>文件夹说明</h2>
      <table>
        <thead><tr><th>文件夹</th><th>放什么</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )
    return {
        "root": root,
        "home": home,
        "record": record,
        "links": links,
        "chrome_profile": root / "00_入口" / ".chrome-profile",
    }


def locate_aerospace():
    candidates = [
        shutil.which("aerospace"),
        "/opt/homebrew/bin/aerospace",
        "/usr/local/bin/aerospace",
    ]
    for item in candidates:
        if item and pathlib.Path(item).exists():
            return str(pathlib.Path(item))
    return None


def aerospace_available(aero):
    proc = run([aero, "list-workspaces", "--focused"], timeout=4)
    return proc.returncode == 0, (proc.stdout or proc.stderr).strip()


def focused_workspace(aero):
    proc = run([aero, "list-workspaces", "--focused"], timeout=4)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip().splitlines()[0].strip() if proc.stdout.strip() else None


def workspace_window_count(aero, workspace):
    proc = run([aero, "list-windows", "--workspace", workspace, "--count"], timeout=5)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    text = proc.stdout.strip() or "0"
    return int(text)


def ensure_aerospace_ready():
    aero = locate_aerospace()
    if not aero:
        safe_fail(
            "未检测到免费组件 AeroSpace。\n"
            "V0.2 不使用不可靠的原生 Mission Control 猜测方案；没有 AeroSpace 就无法确认独立项目工作区。\n"
            "请先运行 install.command，或安装 AeroSpace 后重试。"
        )

    ok, detail = aerospace_available(aero)
    if ok:
        return aero

    subprocess.run(["/usr/bin/open", "-g", "-a", "AeroSpace"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(12):
        time.sleep(0.5)
        ok, detail = aerospace_available(aero)
        if ok:
            return aero

    safe_fail(
        "AeroSpace 已安装但当前不可用，可能还没授权辅助功能权限或没有正常启动。\n"
        f"检测信息：{detail or '无输出'}\n"
        "请打开 AeroSpace 并按系统提示授权，然后重试。"
    )


def ensure_backend(config):
    backend = str(config.get("spaceBackend", "aerospace")).strip().lower()
    if backend != "aerospace":
        safe_fail(
            f"当前配置 spaceBackend={backend!r}，不是 V0.2 支持的安全后端。\n"
            "原生 macOS Mission Control 无公开 API 可稳定创建、命名、复用并验证 Space，所以本版本不会用它打开项目窗口。"
        )


def ensure_chrome():
    chrome_app = pathlib.Path("/Applications/Google Chrome.app")
    if not chrome_app.exists():
        safe_fail("未检测到 Google Chrome。请先安装 Chrome；本启动器不会退回 open URL，以免污染当前浏览器窗口。")


def switch_workspace(aero, workspace):
    before = focused_workspace(aero)
    proc = run([aero, "workspace", workspace], timeout=8)
    if proc.returncode != 0:
        safe_fail(
            "未能切换/创建 AeroSpace 项目工作区。\n"
            f"目标工作区：{workspace}\n"
            f"当前工作区：{before or '未知'}\n"
            f"错误信息：{(proc.stderr or proc.stdout).strip() or '无输出'}"
        )
    for _ in range(20):
        time.sleep(0.2)
        if focused_workspace(aero) == workspace:
            return
    safe_fail(f"AeroSpace 没有确认当前已进入项目工作区 {workspace}。")


def launch_chrome(plan, config):
    plan["chrome_profile"].mkdir(parents=True, exist_ok=True)
    urls = [file_url(plan["home"])]
    urls.extend(item["url"] for item in plan["links"])
    cmd = [
        "/usr/bin/open",
        "-n",
        "-a",
        "Google Chrome",
        "--args",
        f"--user-data-dir={plan['chrome_profile']}",
        "--no-first-run",
        "--new-window",
    ] + urls
    proc = run(cmd, timeout=10)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())


def launch_finder(root):
    script = f"""
set targetFolder to POSIX file {osa_quote(str(root))} as alias
tell application "Finder"
    make new Finder window to targetFolder
    activate
end tell
"""
    proc = run(["/usr/bin/osascript", "-e", script], timeout=10)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())


def run_check(config):
    ensure_backend(config)
    ensure_chrome()
    aero = ensure_aerospace_ready()
    focused = focused_workspace(aero)
    print(json.dumps({"ok": True, "backend": "aerospace", "aerospace": aero, "focusedWorkspace": focused}, ensure_ascii=False, indent=2))


def launch(config):
    ensure_backend(config)
    ensure_chrome()
    plan = prepare_workspace(config)
    aero = ensure_aerospace_ready()
    workspace = str(config.get("workspaceName", "OPC")).strip() or "OPC"

    switch_workspace(aero, workspace)
    try:
        existing = workspace_window_count(aero, workspace)
    except Exception as exc:
        safe_fail(
            "已切换到项目工作区，但无法验证该工作区的窗口列表。\n"
            f"错误信息：{exc}"
        )
    if existing > 0:
        notify(f"已切回 {workspace} 项目工位，检测到已有窗口，本次不重复打开。")
        print(f"Workspace {workspace} already has {existing} window(s).")
        return

    try:
        launch_chrome(plan, config)
        time.sleep(1.0)
        if focused_workspace(aero) != workspace:
            raise RuntimeError(f"打开 Chrome 后焦点离开项目工作区：{focused_workspace(aero)}")
        launch_finder(plan["root"])
    except Exception as exc:
        dialog(
            "项目窗口打开中止",
            "已经先进入项目工作区，但打开项目窗口时发生错误。\n"
            f"{exc}\n\n不会继续打开更多窗口。",
        )
        raise

    time.sleep(2.0)
    after = workspace_window_count(aero, workspace)
    if after < 1:
        dialog(
            "项目窗口验证异常",
            "启动器已尝试在项目工作区打开窗口，但 AeroSpace 未检测到窗口。请把这个提示发给 Ryan 复核。",
        )
        sys.exit(3)
    notify(f"{config['projectName']} 已进入独立工作区 {workspace}。")
    print(f"Launched {config['projectName']} in workspace {workspace}; windows detected: {after}")


def dry_run(config, config_path):
    root = workspace_root(config)
    payload = {
        "config": str(config_path),
        "projectName": config.get("projectName"),
        "workspaceRoot": str(root),
        "workspaceName": config.get("workspaceName", "OPC"),
        "spaceBackend": config.get("spaceBackend", "aerospace"),
        "homeHtml": str(root / "00_入口" / "OPC工位首页.html"),
        "links": link_items(config),
        "folders": config.get("folders", []),
        "safety": [
            "先验证 AeroSpace，再切换/创建命名工作区",
            "确认已进入项目工作区后才打开 Chrome/Finder",
            "Chrome 使用独立 user-data-dir，不向当前 Chrome 窗口加标签",
            "工作区已有窗口时只切换，不重复打开",
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main():
    if len(sys.argv) < 3:
        safe_fail("启动参数错误。")
    config_path = sys.argv[1]
    args = [arg for arg in sys.argv[3:] if arg != "--from-background"]
    config, config_file = load_config(config_path)

    if "--simulate-space-failure" in args:
        safe_fail("模拟测试：新建/切换独立项目工作区失败。")
    if "--dry-run" in args:
        dry_run(config, config_file)
        return
    if "--prepare-only" in args:
        plan = prepare_workspace(config)
        print(f"Prepared workspace: {plan['root']}")
        notify(f"{config['projectName']} 文件夹和工位首页已准备好。")
        return
    if "--check" in args:
        run_check(config)
        return
    launch(config)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        dialog("OPC工位启动器异常", f"{exc}")
        sys.exit(1)
PY
