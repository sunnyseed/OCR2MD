"""从 cell_box_list + table_ocr_pred 重建表格结构。

结构模型给的 pred_html 已经拍板，且丢失了坐标。RT-DETR 的单元格框会偶发越界
——实测某张表 10 个表头格里 5 个纵向吞掉了下一行，表头与首行数据挤进同一个
<td>；因为 HTML 里文本已拼成一串、没有坐标，事后无法拆回去。

本模块回到检测框上重建：边界聚类投票出行列网格，越界的格子按“图上那条线确实
画了”拆开，再用文字框坐标把文本投回格子。判据用图而不是投票数，是因为真正的
合并单元格同样跨越高票边界，只有“线画没画”能区分二者。

无框线表的格子贴着文字而非框线，重建不可靠，grid_confidence 会挡下来并让调用
方退回 pred_html。
"""
import cv2
import numpy as np


def dark_mask(img_path: str, threshold: int = 200):
    """原图的布尔暗图。取最小通道而非亮度，绿色表格线才算得上“暗”。

    表头下那条青绿线亮度 148、最小通道 103；中性灰水印两者都在 220 以上，不会
    被误判成线条。
    """
    img = cv2.imread(img_path)
    if img is None:
        return None
    return img.min(axis=2) < threshold


def cluster_edges(values, tol=6):
    """把邻近的格子边聚成一条网格线。返回 [(坐标, 票数)]，按坐标升序。"""
    if len(values) == 0:
        return []
    vs = sorted(float(v) for v in values)
    groups, cur = [], [vs[0]]
    for v in vs[1:]:
        if v - cur[-1] <= tol:
            cur.append(v)
        else:
            groups.append(cur)
            cur = [v]
    groups.append(cur)
    return [(float(np.median(g)), len(g)) for g in groups]


def line_drawn(dark, x1, x2, y, tol=2, cover=0.6):
    """图上 y 附近横跨 [x1,x2) 是否真有一条线。dark 为布尔图(暗=True)。"""
    h, w = dark.shape
    y1, y2 = max(0, int(y) - tol), min(h, int(y) + tol + 1)
    x1, x2 = max(0, int(x1)), min(w, int(x2))
    if y2 <= y1 or x2 - x1 < 8:
        return False
    return bool((dark[y1:y2, x1:x2].mean(axis=1) >= cover).any())


def line_drawn_v(dark, y1, y2, x, tol=2, cover=0.6):
    """竖线版本。"""
    h, w = dark.shape
    x1, x2 = max(0, int(x) - tol), min(w, int(x) + tol + 1)
    y1, y2 = max(0, int(y1)), min(h, int(y2))
    if x2 <= x1 or y2 - y1 < 8:
        return False
    return bool((dark[y1:y2, x1:x2].mean(axis=0) >= cover).any())


def _prune_lines(lines, dark, lo, hi, vertical, min_votes=2):
    """丢掉单票的假网格线;但图上真画了一条贯穿的线就留下。首尾恒留。"""
    kept = []
    for i, (coord, votes) in enumerate(lines):
        if i in (0, len(lines) - 1) or votes >= min_votes:
            kept.append((coord, votes))
        elif (line_drawn_v(dark, lo, hi, coord, cover=0.5) if vertical
              else line_drawn(dark, lo, hi, coord, cover=0.5)):
            kept.append((coord, votes))
    return kept


def _snap(value, lines):
    return int(np.argmin([abs(value - c) for c, _ in lines]))


def grid_confidence(lines_x, lines_y, boxes, quorum=3):
    """格子边落在高票网格线上的比例。

    有框线表的格子彼此共边,票数集中;无框线表的格子贴着文字,边各不相同、
    全是低票——那种表重建不可靠,应退回 pred_html。
    """
    hit = total = 0
    for lines, edges in ((lines_x, (0, 2)), (lines_y, (1, 3))):
        for b in boxes:
            for e in edges:
                total += 1
                if lines[_snap(b[e], lines)][1] >= quorum:
                    hit += 1
    return hit / total if total else 0.0


def build_grid(cell_boxes, rec_boxes, rec_texts, dark, min_votes=3, min_confidence=0.6):
    """重建表格结构,返回 rows: list[list[str]]。

    dark 为原图布尔暗图(最小通道,彩色线也算暗),用于校验线条是否真实存在。
    置信度不足时返回 [],调用方应退回 pred_html。
    """
    if len(cell_boxes) == 0:
        return []

    boxes = [[float(v) for v in b[:4]] for b in cell_boxes]
    raw_y = cluster_edges([b[1] for b in boxes] + [b[3] for b in boxes])
    raw_x = cluster_edges([b[0] for b in boxes] + [b[2] for b in boxes])
    if len(raw_y) < 2 or len(raw_x) < 2:
        return []
    if grid_confidence(raw_x, raw_y, boxes) < min_confidence:
        return []

    top, bot = min(b[1] for b in boxes), max(b[3] for b in boxes)
    left, right = min(b[0] for b in boxes), max(b[2] for b in boxes)
    ylines = _prune_lines(raw_y, dark, left, right, vertical=False)
    xlines = _prune_lines(raw_x, dark, top, bot, vertical=True)
    if len(ylines) < 2 or len(xlines) < 2:
        return []

    # 每个格子落到网格索引上，越界的按“图上确有线”拆开
    placed = []  # (r1, r2, c1, c2)
    for x1, y1, x2, y2 in boxes:
        r1, r2 = _snap(y1, ylines), _snap(y2, ylines)
        c1, c2 = _snap(x1, xlines), _snap(x2, xlines)
        if r2 <= r1 or c2 <= c1:
            continue
        rcuts = [r1] + [
            r for r in range(r1 + 1, r2)
            if ylines[r][1] >= min_votes and line_drawn(dark, x1, x2, ylines[r][0])
        ] + [r2]
        ccuts = [c1] + [
            c for c in range(c1 + 1, c2)
            if xlines[c][1] >= min_votes and line_drawn_v(dark, y1, y2, xlines[c][0])
        ] + [c2]
        for a, b in zip(rcuts, rcuts[1:]):
            for c, d in zip(ccuts, ccuts[1:]):
                placed.append((a, b, c, d))

    # 文字框按重叠面积投进格子
    texts = {}
    for box, txt in zip(rec_boxes, rec_texts):
        tx1, ty1, tx2, ty2 = (float(v) for v in box[:4])
        area = max(1.0, (tx2 - tx1) * (ty2 - ty1))
        best, best_ov = None, 0.0
        for cell in placed:
            r1, r2, c1, c2 = cell
            cy1, cy2 = ylines[r1][0], ylines[r2][0]
            cx1, cx2 = xlines[c1][0], xlines[c2][0]
            ov = max(0.0, min(tx2, cx2) - max(tx1, cx1)) * max(0.0, min(ty2, cy2) - max(ty1, cy1))
            if ov > best_ov:
                best, best_ov = cell, ov
        if best is not None and best_ov / area >= 0.3:
            texts.setdefault(best, []).append((ty1, tx1, txt))

    n_rows, n_cols = len(ylines) - 1, len(xlines) - 1
    rows = [["" for _ in range(n_cols)] for _ in range(n_rows)]
    for cell, items in texts.items():
        r1, _, c1, _ = cell
        rows[r1][c1] = " ".join(t for _, _, t in sorted(items))
    return [r for r in rows if any(c.strip() for c in r)]
