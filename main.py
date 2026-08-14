import os
from pathlib import Path
from html.parser import HTMLParser

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"


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
        text_detection_model_name="PP-OCRv6_medium_det",
        text_recognition_model_name="PP-OCRv6_medium_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_formula_recognition=False,
        use_chart_recognition=False,
        use_seal_recognition=False,
    )

    result = pipeline.predict(img_path)

    for res in result:
        parsing = res.get("parsing_res_list", [])
        if not parsing:
            print("未检测到任何内容")
            continue

        md = parsing_res_to_markdown(parsing)
        print(md)

        output = Path(img_path).with_suffix(".md")
        output.write_text(md, encoding="utf-8")
        print(f"\n已保存到 {output}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python main.py <图片路径>")
        sys.exit(1)
    main(sys.argv[1])
