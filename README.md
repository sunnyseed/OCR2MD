# ppocr

基于 PaddleOCR (PP-StructureV3) 的截图转 Markdown 工具。按快捷键截图，自动识别其中的文字与表格，结果写入剪贴板，随手粘贴。

## 功能

- **Cmd+Shift+1** 全局快捷键唤起原生截图选框
- 自动判断文字 / 表格 / 混排版面（PP-StructureV3）
- 表格转为 Markdown 表格，标题转 `##`，正文保留原文，按阅读顺序拼接
- 结果自动写入剪贴板，并弹系统通知
- 支持开机自启（macOS LaunchAgent）

## 环境

- macOS（Apple Silicon）
- Python 3.11（由 uv 管理）
- PaddlePaddle **CPU 版**（Mac 无 NVIDIA GPU，不支持 GPU 版）

## 安装

```bash
uv sync
```

依赖包含 `paddlepaddle`、`paddleocr`、`paddlex[ocr]`、`pynput`。

模型在首次运行时按需自动下载到 `~/.paddlex/official_models/`。国内网络可能无法连通官方托管平台，脚本已内置 `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True` 跳过连通性检测，直接从可用源（ModelScope 等）下载。

## 使用

### 单张图片转 Markdown

```bash
uv run python main.py /path/to/image.png   # 传入图片路径
```

结果打印到终端，并保存为与图片同名的 `.md` 文件。

### 快捷键截图模式

```bash
uv run python capture.py
```

1. 启动后立即注册快捷键，模型在后台加载
2. 看到「PPOcr 就绪」通知后，按 **Cmd+Shift+1**
3. 拖选截图区域 → 自动识别 → 通知「已复制到剪贴板」
4. Cmd+V 粘贴

> 首次需在 **系统设置 → 隐私与安全性 → 辅助功能 / 输入监控** 中授权运行进程（终端或 python 可执行文件）。

## 开机自启（LaunchAgent + .app 壳）

常驻自启用 macOS LaunchAgent。这里有两个**踩过坑、务必注意**的点：

1. **不要让 launchd 直接跑裸 python。** pynput 的全局快捷键需要「辅助功能/输入监控」授权，而 TCC 按「应用身份」记账——裸 python 没有稳定身份。做法是套一个最小 `.app` 壳（Bundle ID `com.ppocr.capture`，adhoc 签名），授权对象是这个壳。壳的主可执行文件**必须是编译的 Mach-O**（launchd 不肯把 shell 脚本当 Bundle 主程序启动），源码即 `launcher.c`，它只负责 `chdir` 到项目目录再 `exec` venv 里的 python 跑 `capture.py`。
2. **日志/工作目录不能放 `~/Documents`（或 `~/Desktop`、`~/Downloads`、iCloud 同步目录）。** 这些是 TCC 保护目录，launchd 在 exec 程序前要先打开 `StandardOutPath`/`StandardErrorPath`，打不开就整个 spawn 失败、报 `EX_CONFIG (78)`——而且**与程序本身无关**，极易误诊。日志一律放 `~/Library/Logs/ppocr/`。

### 一次性安装

```bash
# 1) 编译 + 打包 .app 壳到 ~/Applications（注意 launcher.c 里的项目路径需与实际一致）
mkdir -p ~/Applications/PPOCRCapture.app/Contents/MacOS
cc -O2 -o ~/Applications/PPOCRCapture.app/Contents/MacOS/ppocr-capture launcher.c
cp Info.plist ~/Applications/PPOCRCapture.app/Contents/Info.plist   # 见下方说明，或手写
xattr -cr ~/Applications/PPOCRCapture.app
codesign --force --sign - --identifier com.ppocr.capture ~/Applications/PPOCRCapture.app

# 2) 准备日志目录（非 TCC 保护）
mkdir -p ~/Library/Logs/ppocr

# 3) 安装 LaunchAgent（先把 plist 里的「你的用户名」替换为实际值）
cp com.ppocr.capture.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ppocr.capture.plist
```

`Info.plist` 关键字段：`CFBundleIdentifier=com.ppocr.capture`、`CFBundleExecutable=ppocr-capture`、`CFBundlePackageType=APPL`、`LSUIElement=true`（无 Dock 图标）。

### 授权（让快捷键真正生效）

> 系统设置 → 隐私与安全性 → **辅助功能** 和 **输入监控** → `+` → 添加
> `~/Applications/PPOCRCapture.app`

授权后重启 agent 生效：

```bash
launchctl kickstart -k gui/$(id -u)/com.ppocr.capture
```

确认日志里**不再**出现 `This process is not trusted!` 即为授权成功。

### 日常运维

```bash
# 改了 capture.py 后重启（无需重签 .app、无需重新授权）
launchctl kickstart -k gui/$(id -u)/com.ppocr.capture

# 查看状态 / 退出码（last exit code = 0 或 never exited 为正常）
launchctl print gui/$(id -u)/com.ppocr.capture | grep -E 'state|last exit|pid'

# 看日志
tail -f ~/Library/Logs/ppocr/capture.log     # 识别结果（stdout）
tail -f ~/Library/Logs/ppocr/capture.err.log  # 模型加载 / 报错（stderr）

# 停用
launchctl bootout gui/$(id -u)/com.ppocr.capture
```

> 只有改了 `launcher.c`（需重新 `cc` 编译）、`Info.plist`，或移动/改名 `.app` 时，才需要重新 `codesign` 并回授权面板关掉再打开。只改 `capture.py` 不用。

## 文件说明

| 文件 | 说明 |
|------|------|
| `main.py` | 单张图片 → Markdown（命令行） |
| `capture.py` | 常驻进程：快捷键截图 + 识别 + 剪贴板 |
| `test_hotkey.py` | 快捷键监听最小测试（排查输入监控权限） |
| `launcher.c` | `.app` 壳的主可执行文件源码（Mach-O）：chdir + exec venv python |
| `com.ppocr.capture.plist` | LaunchAgent 配置模板（安装到 `~/Library/LaunchAgents/`） |

## 实现要点

- 识别用 `PPStructureV3`，结果在 `parsing_res_list`，每个区块带 `label`（table/title/text…）和 `content`
- 表格 `content` 是 HTML，用内置 `HTMLParser` 转 Markdown 表格
- 截图调用 macOS 原生 `screencapture -i -s`，剪贴板用 `pbcopy`，通知用 `osascript`
- `capture.py` 先注册快捷键再后台加载模型，避免加载期间快捷键不响应
