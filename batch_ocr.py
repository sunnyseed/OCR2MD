"""批量 OCR 图片清单，复用一次 PPStructureV3 模型并生成审计报告。

清单是 JSON 数组，每项至少包含 ``path``，还可以包含 ``id``、``note``、
``reference``、``source`` 等元数据。该工具只写输出目录，不修改原笔记或原图。

用法：
    uv run python batch_ocr.py manifest.json --output output/pilot
"""

import argparse
import json
import os
import re
import time
from pathlib import Path

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

from main import DET_MODEL, REC_MODEL, parsing_res_to_markdown, preprocess, table_markdowns
from table_grid import dark_mask


def safe_name(value: str) -> str:
    value = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "-", value).strip("-.")
    return value[:80] or "image"


def table_stats(markdown: str) -> tuple[int, int]:
    rows = [line for line in markdown.splitlines() if line.startswith("|") and line.endswith("|")]
    data_rows = [line for line in rows if not re.fullmatch(r"\|[ |\-:]+\|", line)]
    columns = max((line.count("|") - 1 for line in data_rows), default=0)
    return len(data_rows), columns


def run(manifest_path: Path, output_dir: Path) -> int:
    from paddleocr import PPStructureV3

    items = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError("manifest 顶层必须是 JSON 数组")

    output_dir.mkdir(parents=True, exist_ok=True)
    pipeline = PPStructureV3(
        text_detection_model_name=DET_MODEL,
        text_recognition_model_name=REC_MODEL,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_formula_recognition=False,
        use_chart_recognition=False,
        use_seal_recognition=False,
    )

    results = []
    for index, item in enumerate(items, 1):
        image_path = Path(item["path"]).expanduser()
        started = time.time()
        result = {key: value for key, value in item.items() if key != "path"}
        result["path"] = str(image_path)
        result["index"] = index
        processed = None

        try:
            if not image_path.is_file():
                raise FileNotFoundError(image_path)
            dark = dark_mask(str(image_path))
            processed = preprocess(str(image_path))
            parts = []
            labels = []
            for prediction in pipeline.predict(processed):
                parsing = prediction.get("parsing_res_list", [])
                labels.extend(
                    block.label if hasattr(block, "label") else block.get("label", "")
                    for block in parsing
                )
                text = parsing_res_to_markdown(parsing, table_markdowns(prediction, dark))
                if text:
                    parts.append(text)

            markdown = "\n\n".join(parts).strip()
            stem = safe_name(str(item.get("note", image_path.stem)).rsplit("/", 1)[-1].removesuffix(".md"))
            ident = item.get("id", index)
            output_name = f"{index:02d}-id{ident}-{stem}.md"
            (output_dir / output_name).write_text(markdown + "\n", encoding="utf-8")
            rows, columns = table_stats(markdown)
            result.update(
                status="ok",
                output=output_name,
                labels=labels,
                characters=len(markdown),
                table_rows=rows,
                table_columns=columns,
            )
        except Exception as exc:
            result.update(status="error", error=f"{type(exc).__name__}: {exc}")
        finally:
            if processed and processed != str(image_path) and os.path.exists(processed):
                os.unlink(processed)

        result["seconds"] = round(time.time() - started, 2)
        results.append(result)
        print(f"[{index}/{len(items)}] {result['status']} {image_path.name} ({result['seconds']}s)", flush=True)
        (output_dir / "results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    ok = [result for result in results if result["status"] == "ok"]
    lines = [
        "# 表格 OCR 试跑报告",
        "",
        f"- 图片：{len(results)} 张",
        f"- 成功：{len(ok)} 张",
        f"- 失败：{len(results) - len(ok)} 张",
        f"- 总耗时：{sum(result['seconds'] for result in results):.2f} 秒",
        f"- 检测为表格：{sum('table' in result.get('labels', []) for result in ok)} 张",
        "",
        "| 序号 | 来源笔记 | 区块 | 字符 | 表格行×列 | 耗时 | 结果 |",
        "|---:|---|---|---:|---:|---:|---|",
    ]
    for result in results:
        labels = ", ".join(result.get("labels", [])) or "-"
        shape = f"{result.get('table_rows', 0)}×{result.get('table_columns', 0)}"
        output = f"[{result['output']}]({result['output']})" if result.get("output") else result.get("error", "失败")
        lines.append(
            f"| {result['index']} | {result.get('note', '-')} | {labels} | "
            f"{result.get('characters', 0)} | {shape} | {result['seconds']}s | {output} |"
        )
    (output_dir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if len(ok) == len(results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="批量运行 PPStructureV3，并生成 Markdown 和审计报告")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return run(args.manifest, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
