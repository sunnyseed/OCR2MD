#!/bin/bash
# 安装/更新 PPOCRCapture 开机自启（.app 壳 + LaunchAgent）。
#
#   ./install.sh                  安装或更新；.app 壳已存在则复用，不重编译
#   ./install.sh --rebuild-shell  强制重编译 .app 壳（会触发重新授权，见下）
#   ./install.sh --uninstall      卸载 LaunchAgent（保留 .app 壳和日志）
#
# 为什么默认不重编译壳：重编译会换掉 Mach-O 二进制，macOS 大概率视为新程序，
# 屏幕录制/辅助功能授权要重走一遍。壳的唯一作用是给 TCC 一个稳定身份，
# 只要 launcher.c 里的项目路径没变，就没有重编译的理由。
set -euo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$HOME/Applications/PPOCRCapture.app"
PLIST="$HOME/Library/LaunchAgents/com.ppocr.capture.plist"
LABEL="com.ppocr.capture"
UID_NUM="$(id -u)"

rebuild_shell=false
case "${1:-}" in
    --rebuild-shell) rebuild_shell=true ;;
    --uninstall)
        launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
        rm -f "$PLIST"
        echo "已卸载 LaunchAgent。.app 壳和日志保留在："
        echo "  $APP"
        echo "  $HOME/Library/Logs/ppocr/"
        exit 0
        ;;
    "") ;;
    *) echo "未知参数: $1" >&2; exit 64 ;;
esac

# --- 前置检查 -------------------------------------------------------------
if [ ! -x "$PROJ/.venv/bin/python" ]; then
    echo "找不到 $PROJ/.venv/bin/python" >&2
    echo "请先在项目目录执行: uv sync" >&2
    exit 1
fi

# --- 1. .app 壳 -----------------------------------------------------------
if [ ! -e "$APP/Contents/MacOS/ppocr-capture" ] || [ "$rebuild_shell" = true ]; then
    if [ "$rebuild_shell" = true ] && [ -e "$APP" ]; then
        echo "!! 正在重编译 .app 壳，之后需要重新授权屏幕录制和辅助功能"
    fi
    echo "==> 构建 .app 壳: $APP"
    mkdir -p "$APP/Contents/MacOS"
    # 项目路径编译期注入，launcher.c 里因此不含任何机器专属路径
    cc -O2 -DPROJ_DIR="\"$PROJ\"" -o "$APP/Contents/MacOS/ppocr-capture" "$PROJ/launcher.c"
    cp "$PROJ/Info.plist" "$APP/Contents/Info.plist"
    xattr -cr "$APP"
    codesign --force --sign - --identifier "$LABEL" "$APP"
else
    echo "==> .app 壳已存在，跳过编译（要强制重建加 --rebuild-shell）"
    # 壳里编译进去的路径和当前项目目录不一致时，跑起来会 chdir 失败退 70
    if ! strings "$APP/Contents/MacOS/ppocr-capture" | grep -qxF "$PROJ"; then
        echo "!! 警告: 现有壳指向的项目路径与当前目录不符" >&2
        echo "   当前目录: $PROJ" >&2
        echo "   请执行 ./install.sh --rebuild-shell" >&2
    fi
fi

# --- 2. 日志目录 ----------------------------------------------------------
# 必须放 ~/Library/Logs，放 ~/Documents 会因 TCC 导致 launchd spawn 失败(78)
mkdir -p "$HOME/Library/Logs/ppocr"

# --- 3. LaunchAgent -------------------------------------------------------
echo "==> 生成 $PLIST"
mkdir -p "$HOME/Library/LaunchAgents"
sed "s|__HOME__|$HOME|g" "$PROJ/com.ppocr.capture.plist.template" > "$PLIST"
plutil -lint "$PLIST" > /dev/null

echo "==> 重新加载服务"
launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
sleep 1   # bootout 后立刻 bootstrap 会偶发 Input/output error
launchctl bootstrap "gui/$UID_NUM" "$PLIST"

sleep 2
if launchctl list | grep -q "$LABEL"; then
    echo
    echo "完成。服务已启动，模型加载+预热约需 1 分钟。"
    echo "就绪后按 Cmd+Shift+1 截图识别。"
    echo "看日志: tail -f ~/Library/Logs/ppocr/capture.log"
else
    echo "服务未能启动，检查: launchctl print gui/$UID_NUM/$LABEL" >&2
    exit 1
fi
