"""
按 Cmd+Shift+1 触发截图区域选择，识别为 Markdown 并写入剪贴板。
运行: uv run python capture.py
停止: Ctrl+C
"""
import os
import subprocess
import tempfile
import threading

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
            text_detection_model_name="PP-OCRv6_medium_det",
            text_recognition_model_name="PP-OCRv6_medium_rec",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_formula_recognition=False,
            use_chart_recognition=False,
            use_seal_recognition=False,
        )
    _pipeline_ready.set()
    print("模型加载完成，Cmd+Shift+1 可以使用了")
    notify("PPOcr 就绪，按 Cmd+Shift+1 开始截图")


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
        return

    try:
        notify("识别中...")
        result = _pipeline.predict(tmp)

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
            notify("未识别到内容", sound=True)
            return

        md = "\n\n".join(parts)
        subprocess.run(["pbcopy"], input=md.encode("utf-8"), check=True)
        notify(f"已复制到剪贴板（{len(parts)} 个区块）", sound=True)
        print("\n--- 识别结果 ---")
        print(md)
        print("----------------\n")
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def notify(msg: str, sound: bool = False):
    script = f'display notification "{msg}" with title "PPOcr"'
    subprocess.run(["osascript", "-e", script])
    if sound:
        subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"])
    print(msg)


_running = False
_run_lock = threading.Lock()


def on_activate():
    global _running
    with _run_lock:
        if _running:
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
    hotkey = keyboard.GlobalHotKeys({"<cmd>+<shift>+1": on_activate})
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
