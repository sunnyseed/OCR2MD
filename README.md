# PPOCR (OCR2MD)

基于 PaddleOCR (PP-StructureV3) 的截图转 Markdown 工具。
按快捷键截图后，自动识别文字/表格，结果写入剪贴板，直接粘贴可用。

## 1. 当前功能

- 全局快捷键支持：Ctrl+Shift+6 和 Cmd+Shift+6
- 自动识别文字、标题、表格并输出 Markdown
- 自动复制到剪贴板
- 支持开机自启（macOS LaunchAgent）
- 识别时重复按快捷键会提示“上一次识别仍在进行”
- 通知中心不可用时，关键状态会弹 2 秒自动消失提示框兜底

## 2. 运行环境

- macOS（建议 Apple Silicon）
- Python 3.11（由 uv 管理）
- PaddlePaddle CPU 版（macOS 无 NVIDIA GPU）

## 3. 从零安装（无 AI 辅助也可直接照做）

### 3.1 安装基础工具

先安装 Xcode Command Line Tools（如果已安装会提示）：

```bash
xcode-select --install
```

安装 Homebrew（如果已安装可跳过）：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

安装 uv：

```bash
brew install uv
```

### 3.2 拉代码并安装 Python 依赖

```bash
git clone <你的仓库地址>
cd OCR2MD
uv sync
```

项目依赖包含：
- paddlepaddle
- paddleocr
- paddlex[ocr]
- pynput

## 4. 首次运行（推荐先手动跑通）

```bash
uv run python capture.py
```

你会看到以下阶段：

1. 快捷键先注册成功
2. 后台加载模型
3. 首次预热（可能较慢）
4. 显示“PPOcr 就绪”

首次运行常见会下载模型到：
- ~/.paddlex/official_models/

如果网络慢，首次可能需要几十秒到几分钟，这属于正常现象。

## 5. 如何使用

1. 启动程序后，按 Ctrl+Shift+6 或 Cmd+Shift+6
2. 拖选截图区域
3. 等待识别完成
4. 结果自动复制到剪贴板
5. 直接粘贴（Cmd+V）

提示说明：
- 如果你取消截图，会提示“截图已取消”
- 如果当前识别未结束又按了快捷键，会提示“上一次识别仍在进行，请稍候”

## 6. 必须授权的系统权限

请在“系统设置 -> 隐私与安全性”中完成以下授权。

### 6.1 手动运行 capture.py 时

需要给“终端程序”（比如 Terminal 或 iTerm）授权：
- 辅助功能
- 输入监控
- 屏幕录制

### 6.2 开机自启运行时

需要给 PPOCRCapture.app 授权：
- 辅助功能
- 输入监控
- 屏幕录制

说明：
- 通知权限建议开启，但即使通知中心静默，本项目也会弹短提示框兜底
- 若你看不到任何通知，先检查是否开启了专注模式（勿扰）

## 7. 开机自启配置（LaunchAgent + .app 壳）

不要让 launchd 直接跑裸 python。
全局热键权限按“应用身份”记账，稳定做法是用一个最小 .app 壳启动 capture.py。

### 7.1 更新路径（重要）

请先编辑 launcher.c，把以下三处改成你自己的实际路径：

- PROJ
- argv[0]（.venv/bin/python 的绝对路径）
- argv[1]（capture.py 的绝对路径）

如果你本地路径是 /Users/Lithos/...，可不改。

另外，com.ppocr.capture.plist 里默认路径是 /Users/Lithos，其他用户名请先替换：

```bash
sed -i '' "s|/Users/Lithos|$HOME|g" com.ppocr.capture.plist
```

### 7.2 构建并签名 .app

```bash
APP="$HOME/Applications/PPOCRCapture.app"
mkdir -p "$APP/Contents/MacOS"
cc -O2 -o "$APP/Contents/MacOS/ppocr-capture" launcher.c
cp Info.plist "$APP/Contents/Info.plist"
xattr -cr "$APP"
codesign --force --sign - --identifier com.ppocr.capture "$APP"
```

### 7.3 安装 LaunchAgent

```bash
mkdir -p "$HOME/Library/Logs/ppocr"
mkdir -p "$HOME/Library/LaunchAgents"
cp com.ppocr.capture.plist "$HOME/Library/LaunchAgents/com.ppocr.capture.plist"
launchctl bootout gui/$(id -u)/com.ppocr.capture 2>/dev/null || true
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.ppocr.capture.plist"
launchctl kickstart -k gui/$(id -u)/com.ppocr.capture
```

### 7.4 验证是否成功

```bash
launchctl print gui/$(id -u)/com.ppocr.capture | grep -E 'state|pid|last exit'
```

看到 running 或稳定 pid 即表示服务在运行。

## 8. 日常维护命令

重启服务（改了 capture.py 后常用）：

```bash
launchctl kickstart -k gui/$(id -u)/com.ppocr.capture
```

查看输出日志：

```bash
tail -f ~/Library/Logs/ppocr/capture.log
```

查看错误日志：

```bash
tail -f ~/Library/Logs/ppocr/capture.err.log
```

停用自启：

```bash
launchctl bootout gui/$(id -u)/com.ppocr.capture
```

## 9. 常见问题

### 9.1 快捷键无反应

优先检查权限是否给对对象：
- 手动运行时看终端程序权限
- 自启动时看 PPOCRCapture.app 权限

再看错误日志是否有：
- This process is not trusted!

### 9.2 两次识别间隔很长

常见原因：
- 正在首次下载/预热模型
- 上一次识别尚未完成

这是模型耗时，不是程序挂死。日志里如果持续滚动模型加载信息，说明仍在工作。

### 9.3 能复制但看不到系统通知

macOS 可能会静默某些进程通知。
本项目已加短提示框兜底，所以关键状态仍可见。

### 9.4 出现 404 或模型下载相关日志

通常是模型源切换过程导致，程序会自动尝试其他源。
若长期失败，建议检查网络或代理设置后重启服务。

## 10. 文件说明

- main.py：单图转 Markdown（命令行）
- capture.py：常驻进程（快捷键截图 + 识别 + 剪贴板）
- test_hotkey.py：快捷键最小测试脚本
- launcher.c：.app 壳的主可执行文件（Mach-O）
- com.ppocr.capture.plist：LaunchAgent 配置模板
- Info.plist：.app 元数据

## 11. 单图模式（可选）

```bash
uv run python main.py /path/to/image.png
```

输出会打印到终端，并保存同名 .md 文件。
