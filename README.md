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

> 首次需在 **系统设置 → 隐私与安全性 → 输入监控** 中授权运行进程（终端或 python 可执行文件）。

## 开机自启

已提供 LaunchAgent 配置 `com.ppocr.capture.plist`，将其中的 `/path/to/ppocr` 替换为你的实际项目路径后，拷贝到 `~/Library/LaunchAgents/`。

```bash
# 启用（加载 + 开机自启）
launchctl load ~/Library/LaunchAgents/com.ppocr.capture.plist

# 停止并取消自启
launchctl unload ~/Library/LaunchAgents/com.ppocr.capture.plist

# 查看是否运行
launchctl list | grep ppocr

# 看日志
tail -f capture.log
```

**重要：** 常驻进程由 `python` 直接启动，输入监控权限按可执行文件判断，需单独给 venv 的 python 授权：

> 系统设置 → 隐私与安全性 → 输入监控 → `+` → 添加
> `~/.local/share/uv/python/cpython-3.11-macos-aarch64-none/bin/python3.11`

授权后 unload 再 load 一次使其生效。

## 文件说明

| 文件 | 说明 |
|------|------|
| `main.py` | 单张图片 → Markdown（命令行） |
| `capture.py` | 常驻进程：快捷键截图 + 识别 + 剪贴板 |
| `test_hotkey.py` | 快捷键监听最小测试（排查输入监控权限） |
| `com.ppocr.capture.plist` | LaunchAgent 配置（已安装到 `~/Library/LaunchAgents/`） |

## 实现要点

- 识别用 `PPStructureV3`，结果在 `parsing_res_list`，每个区块带 `label`（table/title/text…）和 `content`
- 表格 `content` 是 HTML，用内置 `HTMLParser` 转 Markdown 表格
- 截图调用 macOS 原生 `screencapture -i -s`，剪贴板用 `pbcopy`，通知用 `osascript`
- `capture.py` 先注册快捷键再后台加载模型，避免加载期间快捷键不响应
