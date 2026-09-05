import os
from pathlib import Path
from html.parser import HTMLParser

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

import cv2
import numpy as np

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

# 斜纹水印笔画灰度集中在 221-240，正文在 50-145，白场拉伸即可抹掉水印。
# 215 是实测安全窗口（210-215）的上沿，详见 README 12.9。
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


class TableHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self._current_row = []
        self._current_cell = ""
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._current_row = []
        elif tag in ("td", "th"):
            self._in_cell = True
            self._current_cell = ""

    def handle_endtag(self, tag):
        if tag == "tr":
            if self._current_row:
                self.rows.append(self._current_row)
        elif tag in ("td", "th"):
            self._current_row.append(self._current_cell.strip())
            self._in_cell = False

    def handle_data(self, data):
        if self._in_cell:
            self._current_cell += data


def html_table_to_markdown(html: str) -> str:
    parser = TableHTMLParser()
    parser.feed(html)
    rows = parser.rows
    if not rows:
        return ""

    col_widths = [max(len(str(row[i])) for row in rows if i < len(row)) for i in range(len(rows[0]))]

    def fmt_row(row):
        cells = [str(row[i]) if i < len(row) else "" for i in range(len(rows[0]))]
        return "| " + " | ".join(c.ljust(col_widths[i]) for i, c in enumerate(cells)) + " |"

    lines = [fmt_row(rows[0])]
    lines.append("| " + " | ".join("-" * w for w in col_widths) + " |")
    for row in rows[1:]:
        lines.append(fmt_row(row))
    return "\n".join(lines)


def parsing_res_to_markdown(parsing_res_list: list) -> str:
    parts = []
    for item in parsing_res_list:
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
    return "\n\n".join(parts)


def main(img_path: str):
    from paddleocr import PPStructureV3

    pipeline = PPStructureV3(
        text_detection_model_name=DET_MODEL,
        text_recognition_model_name=REC_MODEL,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_formula_recognition=False,
        use_chart_recognition=False,
        use_seal_recognition=False,
    )

    processed = preprocess(img_path)
    try:
        result = pipeline.predict(processed)

        for res in result:
            parsing = res.get("parsing_res_list", [])
            if not parsing:
                print("未检测到任何内容")
                continue

            md = parsing_res_to_markdown(parsing)
            print(md)

            # 输出仍按原图路径命名，预处理产物只是中间文件
            output = Path(img_path).with_suffix(".md")
            output.write_text(md, encoding="utf-8")
            print(f"\n已保存到 {output}")
    finally:
        if processed != img_path and os.path.exists(processed):
            os.unlink(processed)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python main.py <图片路径>")
        sys.exit(1)
    main(sys.argv[1])
