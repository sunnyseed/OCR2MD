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

from pynput import keyboard

# OCR 逻辑（模型选型、去水印、表格重建、Markdown 拼装）统一由 main.py 提供。
# 这里曾经复制过一份，结果 main.py 修好的表格越界单元格与括号归一化没同步过来，
# 快捷键这条路一度落后三个提交——不要再复制。
from main import (
    DET_MODEL,
    REC_MODEL,
    block_content,
    parsing_res_to_markdown,
    preprocess,
    table_markdowns,
)
from table_grid import dark_mask

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
        dark = dark_mask(tmp)           # 线条校验要看原图，预处理会削弱浅色线
        processed = preprocess(tmp)
        result = _pipeline.predict(processed)
        infer_cost = time.time() - infer_start

        parts = []
        blocks = 0
        for res in result:
            parsing = res.get("parsing_res_list", [])
            blocks += sum(1 for item in parsing if block_content(item))
            text = parsing_res_to_markdown(parsing, table_markdowns(res, dark))
            if text:
                parts.append(text)

        if not parts:
            notify("未识别到内容", sound=True)
            return

        md = "\n\n".join(parts)
        subprocess.run(["pbcopy"], input=md.encode("utf-8"), check=True)
        notify(f"已复制到剪贴板（{blocks} 个区块，{infer_cost:.1f}s）", sound=True)
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
