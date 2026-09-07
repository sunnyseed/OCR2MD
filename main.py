import os
from pathlib import Path
from html.parser import HTMLParser

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

import cv2
import numpy as np

from table_grid import build_grid, dark_mask

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
# 215 是实测安全窗口（210-215）的上沿，详见 README 12.9：低于 205 会误伤正文，
# 高于 220 水印回流。往高的一侧留余量——偏低是静默丢正文，偏高只是多几行看得见
# 的垃圾。
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
    """保留单元格的 rowspan/colspan，供 Markdown 展平时维持列对齐。"""

    def __init__(self):
        super().__init__()
        self.rows = []
        self._current_row = []
        self._current_cell = ""
        self._current_rowspan = 1
        self._current_colspan = 1
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._current_row = []
        elif tag in ("td", "th"):
            attr = dict(attrs)
            self._in_cell = True
            self._current_cell = ""
            self._current_rowspan = max(1, int(attr.get("rowspan", 1)))
            self._current_colspan = max(1, int(attr.get("colspan", 1)))
        elif tag == "br" and self._in_cell:
            self._current_cell += "\n"

    def handle_endtag(self, tag):
        if tag == "tr":
            if self._current_row:
                self.rows.append(self._current_row)
        elif tag in ("td", "th"):
            self._current_row.append(
                (self._current_cell.strip(), self._current_rowspan, self._current_colspan)
            )
            self._in_cell = False

    def handle_data(self, data):
        if self._in_cell:
            self._current_cell += data


def _expand_table_spans(raw_rows: list) -> list[list[str]]:
    """把 HTML 合并单元格展开为空白格；Markdown 本身不支持合并单元格。"""
    rows = []
    pending = {}  # column -> remaining rows occupied by a rowspan

    for raw_row in raw_rows:
        row = {column: "" for column in pending}
        for column in list(pending):
            pending[column] -= 1
            if pending[column] == 0:
                del pending[column]

        column = 0
        for text, rowspan, colspan in raw_row:
            while column in row:
                column += 1
            row[column] = text
            for offset in range(1, colspan):
                row[column + offset] = ""
            if rowspan > 1:
                for offset in range(colspan):
                    pending[column + offset] = max(pending.get(column + offset, 0), rowspan - 1)
            column += colspan
        rows.append(row)

    width = max((max(row, default=-1) + 1 for row in rows), default=0)
    return [[row.get(column, "") for column in range(width)] for row in rows]


def _markdown_cell(value: str) -> str:
    value = " ".join(value.split())
    return value.replace("|", r"\|")


def rows_to_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""

    rows = [[_markdown_cell(cell) for cell in row] for row in rows]
    col_widths = [max(3, max(len(row[i]) for row in rows)) for i in range(len(rows[0]))]

    def fmt_row(row):
        return "| " + " | ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(row)) + " |"

    lines = [fmt_row(rows[0])]
    lines.append("| " + " | ".join("-" * width for width in col_widths) + " |")
    lines.extend(fmt_row(row) for row in rows[1:])
    return "\n".join(lines)


def html_table_to_markdown(html: str) -> str:
    parser = TableHTMLParser()
    parser.feed(html)
    return rows_to_markdown(_expand_table_spans(parser.rows))


def table_markdowns(res, dark) -> list[str]:
    """按 table_res_list 顺序给出每张表的 Markdown。

    优先走检测框重建（能修好 pred_html 里的越界单元格）；重建判定不可靠时
    退回 pred_html，两条路的输出格式一致。

    这里必须自己做括号归一化：网格路径的文本直接取自 rec_texts，不经过
    parsing_res_to_markdown 里对 item.content 的那一次归一化。
    """
    out = []
    for table in res.get("table_res_list", []):
        rows = []
        if dark is not None:
            ocr = table["table_ocr_pred"]
            rows = build_grid(table["cell_box_list"], ocr["rec_boxes"], ocr["rec_texts"], dark)
        md = rows_to_markdown(rows) if rows else html_table_to_markdown(table["pred_html"])
        out.append(normalize_brackets(md) if _NORMALIZE else md)
    return out


def block_label(item) -> str:
    """parsing_res_list 的元素可能是对象也可能是 dict。"""
    return item.label if hasattr(item, "label") else item.get("label", "")


def block_content(item) -> str:
    return item.content if hasattr(item, "content") else item.get("content", "")


def parsing_res_to_markdown(parsing_res_list: list, tables: list[str] | None = None) -> str:
    """tables 为按顺序预先算好的表格 Markdown；不传则退回解析 item 自带的 HTML。"""
    pending = list(tables or [])
    parts = []
    for item in parsing_res_list:
        label = block_label(item)
        content = block_content(item)
        if not content:
            continue
        if _NORMALIZE:
            content = normalize_brackets(content)
        if label == "table":
            parts.append(pending.pop(0) if pending else html_table_to_markdown(content))
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

    dark = dark_mask(img_path)          # 线条校验要看原图，预处理会削弱浅色线
    processed = preprocess(img_path)
    try:
        result = pipeline.predict(processed)

        for res in result:
            parsing = res.get("parsing_res_list", [])
            if not parsing:
                print("未检测到任何内容")
                continue

            md = parsing_res_to_markdown(parsing, table_markdowns(res, dark))
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
