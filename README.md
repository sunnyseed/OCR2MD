# PPOCR (OCR2MD)

基于 PaddleOCR (PP-StructureV3) 的截图转 Markdown 工具。
按快捷键截图后，自动识别文字/表格，结果写入剪贴板，直接粘贴可用。

## 1. 当前功能

- 全局快捷键：Ctrl+Shift+6，同时兼容 Cmd+Shift+6（在 `capture.py` 的 `HOTKEYS` 常量中配置）
- 自动识别文字、标题、表格并输出 Markdown
- 自动复制到剪贴板
- 支持开机自启（macOS LaunchAgent）
- 识别时重复按快捷键会提示“上一次识别仍在进行”
- 通知中心不可用时，关键状态会弹 2 秒自动消失提示框兜底
- 识别前自动做白场拉伸预处理，消除斜纹水印（见 12.9）
- 截图原图自动存档到 `sample/`，供后续调优取样（已在 .gitignore 中排除）

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

1. 启动程序后，按 Ctrl+Shift+6（或 Cmd+Shift+6）
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

### 7.1 一条命令安装

在项目目录执行：

```bash
./install.sh
```

它会自动完成：编译 .app 壳并签名 → 生成 LaunchAgent 配置 → 创建日志目录 → 加载服务。

**不需要手工改任何路径。** 项目路径由 install.sh 在编译时注入 launcher.c，
LaunchAgent 配置由 com.ppocr.capture.plist.template 替换 `__HOME__` 生成。
仓库里的文件因此不含任何机器专属路径，也就不会在提交时互相覆盖。

其他用法：

```bash
./install.sh --rebuild-shell   # 强制重编译 .app 壳
./install.sh --uninstall       # 卸载 LaunchAgent（保留壳和日志）
```

注意 `--rebuild-shell` 会换掉 Mach-O 二进制，macOS 大概率视为新程序，
**屏幕录制和辅助功能授权要重走一遍**。只有项目目录搬家了才需要它；
改 capture.py 不需要重建壳。

### 7.2 手动编译（不用 install.sh 时）

launcher.c 要求编译期指定项目路径，否则直接报错：

```bash
cc -O2 -DPROJ_DIR="\"$PWD\"" -o ppocr-capture launcher.c
```

（编辑器/IDE 在不带这个参数时会报 `缺少 PROJ_DIR`，属预期行为，不是代码坏了。）

### 7.3 验证是否成功

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

如果是**启动时**长时间卡住（进程 CPU 接近 0%），先确认项目目录没被 iCloud 同步，
详见第 12.1 节。单次识别的正常耗时区间见第 12.2 节。

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
- install.sh：一键安装/更新开机自启（见第 7 节）
- launcher.c：.app 壳的主可执行文件（Mach-O），项目路径编译期注入
- com.ppocr.capture.plist.template：LaunchAgent 配置模板，`__HOME__` 由 install.sh 替换
- Info.plist：.app 元数据
- sample/：截图原图存档（运行时自动创建）。**内容可能含内部资料，已在 .gitignore 中排除，不要提交**

## 11. 单图模式（可选）

```bash
uv run python main.py /path/to/image.png
```

输出会打印到终端，并保存同名 .md 文件。

## 12. 性能基准（2026-09-04 实测）

测试机：MacBook Pro (Mac14,5)，Apple M2 Max，8 性能核 + 4 能效核，96 GB 内存，macOS 26.6.2。
测试图：1000×560 中英混排截图，11 行文字（模拟真实截图，STHeiti Light 17px）。

### 12.1 启动慢的真正原因：iCloud 同步

项目最初放在 `~/Documents` 下，而该目录开启了 iCloud「桌面与文稿同步」。
`.venv` 里 6407 个文件每次首读都要经 FileProvider，实测**每个小文件阻塞约 0.56 秒**。

| 操作 | 在 iCloud 同步目录下 | 关闭同步后 |
| --- | --- | --- |
| `import paddle` | 5 分钟未完成 | **3.6 秒** |
| 并发读完 6407 个 venv 文件 | 24 分 24 秒 | 秒级 |
| 读 29 个小 `.pyc`（首次） | 16.25 秒，CPU 占用 0% | — |

现象特征：进程 CPU 接近 0%，`sample` 采样显示时间全花在 `read()` 系统调用上，
同时 `fileproviderd` 占 159% CPU、`bird` 60%、`cloudd` 35%。

**结论：项目目录（尤其是 `.venv`）不要放在 iCloud 同步范围内。**

### 12.2 模型规格是唯一有效的速度变量

纯 OCR（det + rec，不含版面分析）：

| 模型 | 耗时 | 字符准确率 | 备注 |
| --- | --- | --- | --- |
| PP-OCRv6_medium | 10.73s | 99.6% | |
| **PP-OCRv6_small** | **4.07s** | **99.5%** | **当前使用**，差异仅一个冒号 |
| PP-OCRv5_server | 7.02s | 99.6% | **表格场景勿用**，见 12.6 |
| PP-OCRv5_mobile | 7.21s | 99.4% | |
| PP-OCRv6_tiny | 1.31s | 99.1% | **不可用**，见下 |

端到端（本项目实际使用的 PPStructureV3 链路）：

| 配置 | 构建 | 推理 |
| --- | --- | --- |
| PPStructureV3 + PP-OCRv6_medium | 2.1s | **12.92s** |
| PPStructureV3 + PP-OCRv6_small | 1.4s | **5.55s** |

**换 small 可提速 2.3 倍，准确率几乎无损**（99.5% vs 99.6%）。
上表是纯文字场景，表格场景下的差异另有结论，见 12.6——**结论并不相同**。

**已于 2026-09-04 切换为 small**，`capture.py` 与 `main.py` 顶部的 `DET_MODEL` / `REC_MODEL`
两个常量控制，改一处即可切回。切换后实测端到端耗时：

| 测试图 | 切换前(medium) | 切换后(small) |
| --- | --- | --- |
| real.png（纯文字） | 12.92s | **5.46s** |
| hard.png（表格+代码） | 14.99s | **8.16s** |
| table2.png（8×7 数据表） | 15.69s | **8.86s** |

tiny 虽然快 8 倍，但中英混排下会把 `PP-OCR` 认成 `PP-〇CR`、`macOS` 认成 `mac〇S`，
字母 O 与汉字〇 分不清，实际不可用。

### 12.3 两个无效的优化方向（已实测排除）

**换掉 PPStructureV3 用纯 PaddleOCR：不值得。**
版面分析 + 表格模型只占 2.2 秒（12.92s vs 10.73s），换掉仅快 17%，
却会丢失表格转 Markdown 的能力。

**调整 `cpu_threads`：无效。**
默认值 10 略高于 8 个性能核，但实测 8 线程 7.47s、10 线程 7.58s，差异 1.5%，属噪声级别。

### 12.4 性能天花板

`paddle.device.is_compiled_with_cuda()` 返回 `False`——PaddlePaddle 在 macOS ARM 上是纯 CPU 编译，
没有 Metal 后端，M2 Max 的 GPU 与神经网络引擎（ANE）全程闲置。

想动用这部分算力有两条候选路径（ONNX + CoreML、Apple Vision），
**均已完整实测，结论见第 13 节**——两条都不能直接替换现有链路。

### 12.5 依赖体积构成

`.venv` 约 1.0 GB（项目自身代码不足 100 KB）：

| 包 | 大小 | 说明 |
| --- | --- | --- |
| paddle | 424M | `libpaddle.so` 单个就 228M，必需 |
| cv2 | 171M | 其中 57M 是 `libOrbbecSDK`（深度相机驱动，装了三个版本，无用） |
| scipy | 81M | 必需，版面分析与表格识别在用 |
| pandas | 48M | paddlex 基础依赖 |
| sklearn | 36M | 必需，`title_level.py` 在用 |
| modelscope | 28M | paddlex 基础依赖 |

理论可省约 185M（换 opencv-python-headless、删 `PyObjCTest`/`paddle/include`/`paddle/distributed`），
但**对速度没有帮助**——拖慢启动的是文件数量而非体积。优先级低。

### 12.6 表格场景下的模型对比

12.2 的准确率是纯文字场景。表格另测，结论与纯文字**不一致**。

**表格结构与 det/rec 无关。** 两张测试图上，v5_server / v6_medium / v6_small 产出的
区块划分与表格行列数完全相同——结构由 `SLANeXt_wired` + `RT-DETR-L` 决定，
换文本检测/识别模型不影响结构，只影响单元格里的文字。

测试一：5×4 财务表，全角括号（hard.png）

| 模型 | 单元格文字 |
| --- | --- |
| PP-OCRv5_server | 全对 |
| PP-OCRv6_medium | 全对 |
| PP-OCRv6_small | 两处括号全半角混用：`营业收入（亿元)`、`净利润(亿元）` |

测试二：8×7 机构数据表，半角括号（table2.png，合成数据）

| 模型 | 耗时 | 单元格文字 |
| --- | --- | --- |
| PP-OCRv5_server | 13.83s | **两处数字错误**：`267.338`（应为 `267,338`）、`145.927`（应为 `145,927`） |
| PP-OCRv6_medium | 15.69s | 全对 |
| **PP-OCRv6_small** | **8.93s** | **全对** |

**v5_server 会把千分位逗号读成小数点。** 在机构数据表里 `267,338` 变成 `267.338`
是量级错误（二十六万 → 不到三百）。这比 v6_small 的全角括号问题严重得多。

因此表格场景下的排序是：

**PP-OCRv6_small（最快，数字全对）> PP-OCRv6_medium（全对但最慢）> PP-OCRv5_server（有数字错误）**

注意这与 12.2 纯文字场景的结论不同：纯文字下 v5_server 是 7.02s / 99.6%，看起来是个
不错的折中；但一旦涉及表格数字就不能用。**不要因为纯文字的数据去选 v5_server。**

### 12.7 三个模型共有的表格结构缺陷

table2.png 中的「合计」行，三个模型**全部识别错误**，表现完全一致：

```
| 机构F   | 671.12 | 588.40 | 2.06% | 145,927 | 26 | 姓名F | 合计 |
|          |        |        |       |         |    |      |      |
```

「合计」被并入上一行的「负责人」列，末尾多出一整行空行。

这是 `SLANeXt_wired` 表格结构模型的问题，与 det/rec 选择无关，换任何模型都复现。
**截取带合计行/汇总行的表格时需要人工核对最后一行。**

### 12.8 括号归一化后处理

small 唯一稳定的失分是全角/半角括号混用——同一个词里可能出现 `营业收入（亿元)`
这样一半全角一半半角的结果。识别完成后统一做一次归一化，全部转为半角。

实现在 `capture.py` 与 `main.py` 顶部：

```python
_BRACKETS = str.maketrans({
    "\uff08": "(", "\uff09": ")",   # （）
    "\uff3b": "[", "\uff3d": "]",   # ［］
    "\uff5b": "{", "\uff5d": "}",   # ｛｝
})

def normalize_brackets(text: str) -> str:
    return text.translate(_BRACKETS)

_NORMALIZE = "small" in REC_MODEL
```

在 `parsing_res_list` 遍历中对每个 `content` 应用，表格分支同样生效
（表格内容是 HTML，标签用的是尖括号 `<>`，不受影响）。

**只处理全角 ASCII 括号**（U+FF08/FF09、U+FF3B/FF3D、U+FF5B/FF5D），
不动 `【】`、`《》`、`〈〉`——这些是 CJK 专有符号，没有对应的半角形式，
转成 `[]` 会改变原意，而且它们本来也不是 OCR 的误识别来源。

`_NORMALIZE` 绑定在模型名上：切回 medium 时自动关闭。
medium 的括号本来就准，此时归一化只会把正确的全角括号改坏。

**已知代价**：原文里合法的全角括号会被一并转成半角。这是用一点保真度
换取输出一致性的取舍——粘贴到 Markdown 里时半角括号更常用。

验证用例：

| 输入 | 输出 |
| --- | --- |
| `营业收入（亿元)` | `营业收入(亿元)` |
| `净利润(亿元）` | `净利润(亿元)` |
| `【重要】《报告》〈附件〉` | 不变 |
| `list［str］` | `list[str]` |

### 12.9 斜纹水印预处理

部分内部截图带有平铺的斜纹文字水印（机构名 + 编号 + 保密提示语）。
实测水印笔画灰度集中在 **221–240**，正文在 **50–145**，分离度足够，
一次白场拉伸即可抹掉，**耗时 1.2 毫秒**，不需要专门的去水印模型。

```python
WHITE_POINT = 215
_LEVEL_LUT = np.array(
    [min(255, round(min(i, WHITE_POINT) / WHITE_POINT * 255)) for i in range(256)],
    dtype=np.uint8,
)
```

#### 效果（4 张真实截图，PP-OCRv6_small）

| 样例 | 原图水印杂字 | 预处理后 | 正文关键词命中 |
| --- | --- | --- | --- |
| A 投屏截图 | 7 | **0** | 25/25 → 25/25 |
| B 数据表 | 0 | 0 | 23/23 → 23/23 |
| C 图文长文 | 44 | **0** | 18/18 → 18/18 |
| D 图文长文 | 21 | **0** | 12/12 → 12/12 |

同样四张用 medium：原图杂字 7 / 0 / 66 / 56，且长图那张在原图上**漏掉了一个正文词组**。
**medium 比 small 更容易被水印带偏**，加预处理后才追平。

#### 阈值 215 是实测出来的

| 白场值 | 结果 |
| --- | --- |
| 205 | ❌ 样例 A 丢失一个正文词 |
| 210 / 212 / 213 / 215 | ✅ 四张全部清零、全部命中 |
| 220 | ⚠️ 样例 A 水印回流 7 字 |
| 225 | ⚠️ 回流 7 和 10 字 |

安全窗口 210–215 且是平的（212、213 都验证过）。取上沿 215 的原因是**两侧失效模式不对称**：
偏低会静默丢正文，偏高只是多几行看得见的垃圾。

#### 已排除的其他做法

| 做法 | 结果 |
| --- | --- |
| 硬裁切（≥阈值变白，其余不动） | ❌ 更差。样例 A 漏 7 个水印字且丢 2 个关键词——硬裁切在水印抗锯齿边缘留下细轮廓，仍被检测器捕捉 |
| 分段曲线（<180 不动，180–215 拉伸） | 与直接拉伸无差别（干净图 98.39% vs 98.38%） |
| CLAHE 局部对比度增强 | ❌ 95.9%（原图 97.7%）——把淡水印一起增强了 |
| 自适应阈值二值化 | ❌ 90.3% |
| 直接 2 倍放大 | ❌ 92.8%——水印变清晰后更易被检出 |

#### 代价

无水印的干净截图上基本无损（纯文字图与数据表 100% 一致），
唯一固定代价是**浅灰次要文字**——灰度 160 的文字被提亮到 190，对比度下降：

```
原图:        通用 | 已开启 | ... | 32 个App | ...清理缓存文件。
预处理后:     通用 | 三天启 | ... | 32App   | ...清理缓存文件
```

一整张 UI 截图错 3 个字符，且四种预处理变体都有，调不掉。

#### 为什么不先判断有没有水印

试过三个判据，都不可靠：

| 判据 | 失败原因 |
| --- | --- |
| 浅灰带占比 | 水印图 22% vs 浅灰 UI 11%，只差 2 倍，一个大面积灰面板就能越线 |
| 细笔画占比 | 纯文字图上是 100%（浅灰带里只剩抗锯齿边缘），完全失效 |
| 斜向能量比（FFT） | 干净图 1.50–1.65 反而**高于**水印图 1.545 |

组合判据（带 > 5% 且细笔画 > 25%）在稀疏水印上漏检 2/4。
既然无条件预处理的代价只有 3 个字符，就不值得引入一个会误判的判据。

### 12.10 截图原图存档

每次截图的**原图**（预处理前）会存到 `sample/`，文件名是毫秒级时间戳，
同毫秒重复触发时追加 `_1`、`_2` 后缀，不会静默覆盖。

用途是积累真实样本，供后续调整白场阈值、评估新模型时回归验证。

**这个目录已加入 .gitignore。** 内容是你日常截取的屏幕区域，
可能包含未公开的内部资料，不要提交、不要同步到云端。
需要清理时直接 `rm -rf sample/`，程序会在下次截图时重建。

## 13. 已验证但不采用的加速路径

以下两条都做过完整实测（2026-09-04）。记录在此，避免日后重复探索。

### 13.1 ONNX + CoreML ExecutionProvider：不可行

PaddleX 内置 `ONNXRuntimeRunner`（`paddlex/inference/models/runners/onnxruntime_runner.py`），
其 `ONNXRuntimeRunnerConfig.providers` 可直接指定 `CoreMLExecutionProvider`，
所以工作量并不大。onnxruntime 1.29.0 的 macOS ARM wheel 也确实带 CoreML EP。

**致命问题：表格结构模型无法加载。**

用 `paddle2onnx 2.1.0` 转换：

| 模型 | 转换 | ORT 加载 |
| --- | --- | --- |
| PP-OCRv6_medium_det / _rec | ✅ | ✅ |
| PP-DocLayout_plus-L | ✅ | ✅ |
| RT-DETR-L_wired_table_cell_det | ✅ | ✅ |
| SLANeXt_wired（opset 16 / 17 / 19） | ✅ | ❌ |
| SLANet_plus（opset 16） | ✅ | ❌ |

两个表格模型、三个 opset，报错完全一致：

```
Node (Loop.0) Op (Loop) [TypeInferenceError]
Output: p2o.pd_op.logical_and.0.0 [ShapeInferenceError]
Mismatch between number of inferred and declared dimensions. inferred=1 declared=0
```

表格结构识别是自回归解码，导出后为 `Loop` 节点，paddle2onnx 生成的循环条件张量
声明为标量（rank 0）但实际推断为 rank 1。属转换器 bug，换 opset 无效。

**即使绕过表格，加速也不成立。** 能加载的 4 个模型 CPU EP vs CoreML EP：

| 模型 | CPU EP | CoreML EP | 提升 |
| --- | --- | --- | --- |
| PP-OCRv6_medium_det | 0.484s | 0.483s | **0%** |
| PP-OCRv6_medium_rec | 0.247s | 0.230s | 7% |
| PP-DocLayout_plus-L | 0.416s | 0.215s | 1.9× |
| RT-DETR-L 表格单元格 | 0.278s | 0.158s | 1.8× |

原因：det / rec 的输入是动态尺寸（`[N,3,dyn,dyn]`），CoreML 基本全量回退 CPU；
只有固定尺寸的 layout（800×800）与 RT-DETR（640×640）拿到了加速。
而 det + rec 恰恰是大头——占端到端 12.92 秒中的 10.73 秒。**加速的都是小头。**

数值精度方面（供参考，非阻塞项）：

- det 最大绝对误差 1.6e-07、rec 2.9e-05，可忽略
- layout 检出框数量与类别完全一致，置信度差 0.009，坐标差 1.1px / 800px
- RT-DETR 表格单元格：CPU 检出 19 个、CoreML 20 个。系阈值边界翻转
  （置信度全部挤在 0.28–0.40，CoreML 系统性高约 0.004，第 20 个框正好卡在 0.3 两侧），
  源于 ANE 只支持 FP16。非系统性劣化，但对表格而言多一格少一格会改变结构。

### 13.2 Apple Vision framework：快 35 倍，但丢失表格能力

macOS 自带 Vision OCR 走 ANE，经 `pyobjc-framework-Vision` 调用。

干净截图（real.png，17px）：

| 引擎 | 耗时 | 字符准确率 |
| --- | --- | --- |
| PP-OCRv6_medium | 10.73s | 99.6% |
| **Apple Vision (accurate)** | **0.31s** | **99.8%** |
| Apple Vision (fast) | 0.072s | 58.2%（不可用） |

但换成密集小字 + 表格 + 代码块的难图（hard.png，13px）后暴露硬伤：

| | Apple Vision | PPStructureV3 + medium |
| --- | --- | --- |
| 耗时 | 0.28s | 14.99s |
| 表格 | ❌ 无结构，且按**列**顺序输出（「同比」整列跑到最后） | ✅ 完整 HTML table，行列全对 |
| 代码块 | ❌ `list[str]`→`List Istrl`，ASCII 括号变全角，`O(1)`→`0（1）` | ✅ 仅 `->` 认成 `>` |
| 中文小字 | ❌ 本季**废**、**維**持（繁体）、未达预期收（漏「益」） | ✅ 全对 |

代码块受损源于 `usesLanguageCorrection`，可关闭，但关闭后中文准确率下降。
表格按列输出无解——Vision 只返回文本行与坐标，不做版面分析。

**结论：不能替换 PPStructureV3，但适合做快路径**——
普通文字截图走 Vision（0.3 秒），检测到表格时再回退 PPStructureV3。尚未实现。

### 13.3 当前建议的优先级

1. ~~**换 PP-OCRv6_small**~~：**已完成**（2026-09-04），见 12.2、12.6、12.8
2. **Vision 快路径**：覆盖大部分纯文字截图场景，需实现表格检测分流
3. ~~ONNX + CoreML~~：已排除，见 13.1
