"""
按 Ctrl+Shift+6 触发截图区域选择，识别为 Markdown 并写入剪贴板。
兼容 Cmd+Shift+6，避免键位误按导致无响应。
运行: uv run python capture.py
停止: Ctrl+C
"""
import os
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

import cv2
import numpy as np
from pynput import keyboard

# Ctrl 与 Cmd 两个键位都注册，两种手感都能触发（PR #1 引入的做法，此处恢复）。
# 选 6 的依据：本机 Cmd+Shift+2/4/5 已被截图功能占用（2=拷贝选区、4=选区截图、
# 5=截屏选项），6 空闲——系统默认是 Touch Bar 截图，而 Mac14,5 无 Touch Bar。
# 若与第三方工具（Raycast/Magnet 的绑定无法程序化枚举）冲突，改成 7/8/9/0——
# 这几个完全没有系统默认，比 6 少一层依赖假设。
HOTKEYS = ["<ctrl>+<shift>+6", "<cmd>+<shift>+6"]


def _label(hk: str) -> str:
    return hk.replace("<ctrl>", "Ctrl").replace("<cmd>", "Cmd").replace("<shift>", "Shift")


_HOTKEY_LABEL = " 或 ".join(_label(h) for h in HOTKEYS)

# 截图原图存档目录，供后续调优取样。内容可能含内部资料，已在 .gitignore 中排除。
SAMPLE_DIR = Path(__file__).resolve().parent / "sample"

# small 比 medium 快约 2.3 倍，纯文字与表格数字均无损（见 README 12.2 / 12.6）。
DET_MODEL = "PP-OCRv6_small_det"
REC_MODEL = "PP-OCRv6_small_rec"

# small 唯一稳定的失分是全角/半角括号混用（如“营业收入（亿元)”），做一次归一化。
# 只处理全角 ASCII 括号（U+FF08 等），不动【】《》〈〉——那些是 CJK 专有符号，
# 换成半角会改变原意，不属于 OCR 误识别。
_BRACKETS = str.maketrans({
    "\uff08": "(", "\uff09": ")",   # （）
    "\uff3b": "[", "\uff3d": "]",   # ［］
    "\uff5b": "{", "\uff5d": "}",   # ｛｝
})


def normalize_brackets(text: str) -> str:
    """把全角 ASCII 括号统一成半角。仅在使用 small 模型时启用。"""
    return text.translate(_BRACKETS)


# 换回 medium 时应关掉归一化：medium 的括号本来就准，归一化只会改坏原文。
_NORMALIZE = "small" in REC_MODEL

# 斜纹水印的笔画灰度集中在 221-240，正文在 50-145，白场拉伸即可抹掉水印。
# 215 是实测出来的安全窗口（210-215）上沿：低于 205 会误伤正文，高于 220 水印回流。
# 往高的一侧留余量——偏低是静默丢正文，偏高只是多几行看得见的垃圾。
WHITE_POINT = 215
_LEVEL_LUT = np.array(
    [min(255, round(min(i, WHITE_POINT) / WHITE_POINT * 255)) for i in range(256)],
    dtype=np.uint8,
)


def preprocess(img_path: str) -> str:
    """白场拉伸去水印。返回处理后图片路径；失败时原样返回，不阻断识别。"""
    try:
        src = cv2.imread(img_path)
        if src is None:
            return img_path
        gray = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
        out = cv2.cvtColor(cv2.LUT(gray, _LEVEL_LUT), cv2.COLOR_GRAY2BGR)
        dst = f"{os.path.splitext(img_path)[0]}_pp.png"
        cv2.imwrite(dst, out)
        return dst
    except Exception as e:
        print(f"[preprocess] failed, 用原图继续: {e}")
        return img_path


def archive_sample(img_path: str) -> None:
    """把截图原图（未经预处理）存档，作为后续调优样本。失败不影响识别。"""
    try:
        SAMPLE_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        suffix = os.path.splitext(img_path)[1] or ".png"
        dst = SAMPLE_DIR / f"{stamp}{suffix}"
        # 同毫秒内重复触发时不要静默覆盖已有样本
        n = 1
        while dst.exists():
            dst = SAMPLE_DIR / f"{stamp}_{n}{suffix}"
            n += 1
        shutil.copy2(img_path, dst)
    except Exception as e:
        print(f"[sample] 存档失败: {e}")

_pipeline = None
_pipeline_lock = threading.Lock()
_pipeline_ready = threading.Event()


def load_pipeline_bg():
    global _pipeline
    print("正在后台加载模型...")
    from paddleocr import PPStructureV3
    with _pipeline_lock:
        _pipeline = PPStructureV3(
            text_detection_model_name=DET_MODEL,
            text_recognition_model_name=REC_MODEL,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_formula_recognition=False,
            use_chart_recognition=False,
            use_seal_recognition=False,
        )
    # 真实预热一次，避免首个快捷键触发时才下载/加载子模型导致长时间无响应。
    notify("模型预热中，首次启动可能较慢")
    warmup_start = time.time()
    _warmup_pipeline()
    warmup_cost = time.time() - warmup_start
    _pipeline_ready.set()
    print(f"模型加载完成，{_HOTKEY_LABEL} 可以使用了")
    notify(f"PPOcr 就绪（预热 {warmup_cost:.1f}s），按 {_HOTKEY_LABEL} 开始截图", sound=True)


def _warmup_pipeline():
    from PIL import Image

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        warmup_img = f.name
    try:
        # 用内存生成的空白图片触发一次完整推理链路，避免额外系统权限弹窗。
        Image.new("RGB", (64, 64), (255, 255, 255)).save(warmup_img)
        _pipeline.predict(warmup_img)
    except Exception as e:
        # 预热失败不阻断服务启动，但明确提示后续首轮识别可能变慢或失败。
        notify(f"预热失败：{type(e).__name__}，可继续尝试截图")
        print(f"[warmup] failed: {e}")
    finally:
        if os.path.exists(warmup_img):
            os.unlink(warmup_img)


def html_table_to_markdown(html: str) -> str:
    from html.parser import HTMLParser

    class Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows, self._row, self._cell, self._in = [], [], "", False

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self._row = []
            elif tag in ("td", "th"):
                self._in = True
                self._cell = ""

        def handle_endtag(self, tag):
            if tag == "tr":
                if self._row:
                    self.rows.append(self._row)
            elif tag in ("td", "th"):
                self._row.append(self._cell.strip())
                self._in = False

        def handle_data(self, data):
            if self._in:
                self._cell += data

    p = Parser()
    p.feed(html)
    rows = p.rows
    if not rows:
        return ""
    widths = [max(len(r[i]) for r in rows if i < len(r)) for i in range(len(rows[0]))]

    def fmt(row):
        cells = [row[i] if i < len(row) else "" for i in range(len(rows[0]))]
        return "| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(cells)) + " |"

    lines = [fmt(rows[0]), "| " + " | ".join("-" * w for w in widths) + " |"]
    lines += [fmt(r) for r in rows[1:]]
    return "\n".join(lines)


def run_capture():
    if not _pipeline_ready.is_set():
        notify("模型加载中，请稍候...")
        print("模型尚未加载完成，请稍候")
        return

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = f.name
    os.unlink(tmp)  # 让 screencapture 自己创建文件，取消时不创建

    ret = subprocess.run(["screencapture", "-i", "-s", tmp])
    if ret.returncode != 0 or not os.path.exists(tmp):
        print("截图已取消")
        notify("截图已取消")
        return

    archive_sample(tmp)

    processed = None
    try:
        notify("识别中...")
        infer_start = time.time()
        processed = preprocess(tmp)
        result = _pipeline.predict(processed)
        infer_cost = time.time() - infer_start

        parts = []
        for res in result:
            for item in res.get("parsing_res_list", []):
                label = item.label if hasattr(item, "label") else item.get("label", "")
                content = item.content if hasattr(item, "content") else item.get("content", "")
                if not content:
                    continue
                if _NORMALIZE:
                    content = normalize_brackets(content)
                if label == "table":
                    parts.append(html_table_to_markdown(content))
                elif label == "title":
                    parts.append(f"## {content}")
                else:
                    parts.append(content)

        if not parts:
            notify("未识别到内容", sound=True)
            return

        md = "\n\n".join(parts)
        subprocess.run(["pbcopy"], input=md.encode("utf-8"), check=True)
        notify(f"已复制到剪贴板（{len(parts)} 个区块，{infer_cost:.1f}s）", sound=True)
        print("\n--- 识别结果 ---")
        print(md)
        print("----------------\n")
    except Exception as e:
        notify(f"识别失败：{type(e).__name__}", sound=True)
        print(f"[capture] failed: {e}")
    finally:
        # processed 可能就是 tmp 本身（预处理失败时原样返回），去重后再删
        for f in {tmp, processed} - {None}:
            if os.path.exists(f):
                os.unlink(f)


def _escape_applescript_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def notify(msg: str, sound: bool = False):
    safe = _escape_applescript_text(msg)
    script = f'display notification "{safe}" with title "PPOcr"'
    subprocess.run(["osascript", "-e", script], check=False)
    # 通知中心可能静默第三方进程，关键节点用提示音兜底（不弹窗，避免抢焦点）。
    if sound:
        subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"])
    print(msg)


_running = False
_run_lock = threading.Lock()
_last_busy_notify = 0.0


def on_activate():
    global _running, _last_busy_notify
    with _run_lock:
        if _running:
            now = time.time()
            if now - _last_busy_notify > 2.0:
                notify("上一次识别仍在进行，请稍候")
                _last_busy_notify = now
            return
        _running = True

    def task():
        global _running
        try:
            run_capture()
        finally:
            with _run_lock:
                _running = False

    threading.Thread(target=task, daemon=True).start()


def main():
    # 先注册快捷键
    hotkey = keyboard.GlobalHotKeys({hk: on_activate for hk in HOTKEYS})
    hotkey.start()
    print("快捷键已注册，等待模型加载...")

    # 后台加载模型
    threading.Thread(target=load_pipeline_bg, daemon=True).start()

    print("监听中，按 Ctrl+C 退出")
    try:
        hotkey.join()
    except KeyboardInterrupt:
        print("\n已退出")


if __name__ == "__main__":
    main()
