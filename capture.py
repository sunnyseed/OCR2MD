"""
按 Ctrl+Shift+6 触发截图区域选择，识别为 Markdown 并写入剪贴板。
兼容 Cmd+Shift+6，避免键位误按导致无响应。
运行: uv run python capture.py
停止: Ctrl+C
"""
import os
import subprocess
import tempfile
import threading
import time

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

from pynput import keyboard

_pipeline = None
_pipeline_lock = threading.Lock()
_pipeline_ready = threading.Event()


def load_pipeline_bg():
    global _pipeline
    print("正在后台加载模型...")
    from paddleocr import PPStructureV3
    with _pipeline_lock:
        _pipeline = PPStructureV3(
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
    print("模型加载完成，Ctrl+Shift+6（或 Cmd+Shift+6）可以使用了")
    notify(f"PPOcr 就绪（预热 {warmup_cost:.1f}s），按 Ctrl+Shift+6 开始截图", force_dialog=True)


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

    try:
        notify("识别中...")
        infer_start = time.time()
        result = _pipeline.predict(tmp)
        infer_cost = time.time() - infer_start

        parts = []
        for res in result:
            for item in res.get("parsing_res_list", []):
                label = item.label if hasattr(item, "label") else item.get("label", "")
                content = item.content if hasattr(item, "content") else item.get("content", "")
                if not content:
                    continue
                if label == "table":
                    parts.append(html_table_to_markdown(content))
                elif label == "title":
                    parts.append(f"## {content}")
                else:
                    parts.append(content)

        if not parts:
            notify("未识别到内容", force_dialog=True)
            return

        md = "\n\n".join(parts)
        subprocess.run(["pbcopy"], input=md.encode("utf-8"), check=True)
        notify(f"已复制到剪贴板（{len(parts)} 个区块，{infer_cost:.1f}s）", force_dialog=True)
        print("\n--- 识别结果 ---")
        print(md)
        print("----------------\n")
    except Exception as e:
        notify(f"识别失败：{type(e).__name__}", force_dialog=True)
        print(f"[capture] failed: {e}")
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _escape_applescript_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def notify(msg: str, force_dialog: bool = False):
    safe = _escape_applescript_text(msg)
    script = f'display notification "{safe}" with title "PPOcr"'
    subprocess.run(["osascript", "-e", script], check=False)

    # 某些系统环境下通知中心会静默第三方进程；关键节点加一个自动消失的提示框兜底。
    if force_dialog:
        dialog = (
            f'display dialog "{safe}" with title "PPOcr" '
            'buttons {"知道了"} default button "知道了" giving up after 2'
        )
        subprocess.run(["osascript", "-e", dialog], check=False)
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
    hotkey = keyboard.GlobalHotKeys({
        "<ctrl>+<shift>+6": on_activate,
        "<cmd>+<shift>+6": on_activate,
    })
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
