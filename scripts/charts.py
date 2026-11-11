"""SVG charts drawn from data: weekly bars, a one-week line, and the cause-and-effect diagram."""
import html
import os
import sys
from datetime import date

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.issue import layers  # noqa: E402

UP = "#c8372d"
DOWN = "#2563a8"
FLAT = "#667085"
INK = "#1c2230"
SUB = "#667085"
ACCENT = "#8a6d1f"
SOFT = "#f6f1e3"
W = 340


def esc(text):
    return html.escape(str(text), quote=True)


def fmt_change(change, unit):
    digits, suffix = (2, "ポイント") if unit == "pt" else (1, "%")
    rounded = round(abs(change), digits)
    if rounded == 0:
        return f"±{0:.{digits}f}{suffix}"
    return f"{'▲' if change > 0 else '▼'}{rounded:.{digits}f}{suffix}"


def color_for(change):
    return UP if change > 0 else DOWN if change < 0 else FLAT


def _units(ch):
    return 0.55 if ch.isascii() else 1.0


def wrap(text, limit):
    """Break text into lines of at most `limit` full-width characters (ASCII counts as about half)."""
    lines, current, used = [], "", 0.0
    for ch in str(text):
        if current and used + _units(ch) > limit:
            lines.append(current)
            current, used = "", 0.0
        current += ch
        used += _units(ch)
    lines.append(current)
    return lines


def _svg(height, label, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height:.0f}" width="100%" '
            f'role="img" aria-label="{esc(label)}">{body}</svg>')


def _md(iso):
    d = date.fromisoformat(iso)
    return f"{d.month}/{d.day}"


def bars_svg(items):
    """Risers first, then fallers, each by how unusual the move was. Bar length follows `score`."""
    ups = sorted((i for i in items if i["change"] >= 0), key=lambda i: -i["score"])
    downs = sorted((i for i in items if i["change"] < 0), key=lambda i: -i["score"])
    rows = ups + downs
    top = max((i["score"] for i in rows), default=1) or 1
    centre, half, row_h = 180, 58, 30
    height = row_h * len(rows) + 6
    out = [f'<line x1="{centre}" y1="2" x2="{centre}" y2="{height - 2}" stroke="#b9bfca"/>']
    for k, item in enumerate(rows):
        y = 6 + k * row_h
        colour = color_for(item["change"])
        length = half * item["score"] / top
        x = centre if item["change"] >= 0 else centre - length
        out.append(f'<text x="0" y="{y + 15}" font-size="12" fill="{INK}">{esc(item["name"])}</text>')
        out.append(f'<rect x="{x:.1f}" y="{y + 4}" width="{length:.1f}" height="14" rx="2" fill="{colour}"/>')
        out.append(f'<text x="{W - 2}" y="{y + 15}" font-size="12" font-weight="700" text-anchor="end" '
                   f'fill="{colour}">{esc(fmt_change(item["change"], item["unit"]))}</text>')
    return _svg(height, "今週の動き一覧", "".join(out))


def line_svg(daily, notes, change):
    """One week of closes. `notes` ({date, text}) mark the days something happened."""
    colour = color_for(change)
    days = [d for d, _ in daily]
    values = [v for _, v in daily]
    notes = [n for n in notes if n.get("date") in days]
    left, right, plot_h, line_h = 16, W - 16, 70, 13
    note_lines = [wrap(n["text"], 16) for n in notes]
    top = 10 + sum(len(lines) * line_h + 4 for lines in note_lines)
    bottom = top + plot_h
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0

    def px(k):
        return left + (right - left) * (k / (len(days) - 1) if len(days) > 1 else 0.5)

    def py(v):
        return bottom - 6 - (plot_h - 12) * ((v - lo) / span if hi > lo else 0.5)

    out = [f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#e4e7ec"/>']
    points = " ".join(f"{px(k):.1f},{py(v):.1f}" for k, v in enumerate(values))
    out.append(f'<polyline fill="none" stroke="{colour}" stroke-width="2.5" stroke-linejoin="round" '
               f'stroke-linecap="round" points="{points}"/>')
    out.append(f'<circle cx="{px(len(days) - 1):.1f}" cy="{py(values[-1]):.1f}" r="3" fill="{colour}"/>')

    step = max(1, -(-len(days) // 8))
    shown = sorted(set(range(0, len(days), step)) | {len(days) - 1})
    if len(shown) > 1 and shown[-1] - shown[-2] < step:
        shown.pop(-2)
    for k in shown:
        anchor = "start" if k == 0 and len(days) > 1 else "end" if k == len(days) - 1 and len(days) > 1 else "middle"
        out.append(f'<text x="{px(k):.1f}" y="{bottom + 15}" font-size="10" fill="{SUB}" '
                   f'text-anchor="{anchor}">{esc(_md(days[k]))}</text>')

    y = 10
    for note, lines in zip(notes, note_lines):
        k = days.index(note["date"])
        x = px(k)
        anchor = "start" if x < W / 3 else "end" if x > W * 2 / 3 else "middle"
        spans = "".join(f'<tspan x="{x:.1f}" dy="{line_h if n else 0}">{esc(s)}</tspan>'
                        for n, s in enumerate(lines))
        out.append(f'<text x="{x:.1f}" y="{y + 9}" font-size="10.5" fill="{INK}" text-anchor="{anchor}">{spans}</text>')
        y += len(lines) * line_h + 4
        out.append(f'<line x1="{x:.1f}" y1="{y - 3}" x2="{x:.1f}" y2="{py(values[k]) - 6:.1f}" '
                   f'stroke="{SUB}" stroke-dasharray="2 2"/>')
        out.append(f'<circle cx="{x:.1f}" cy="{py(values[k]):.1f}" r="4.5" fill="#fff" stroke="{colour}" stroke-width="2"/>')
    return _svg(bottom + 22, "1週間の値動き", "".join(out))


_BOX_W = {1: 200, 2: 150, 3: 104}
_GAP_X, _GAP_Y, _LINE = 8, 46, 16


def _node_lines(node, width, instruments):
    limit = int((width - 12) / 12.5)
    if node.get("type") == "instrument":
        inst = instruments[node["instrument"]]
        return wrap(inst["name"], limit), fmt_change(inst["change"], inst["unit"]), color_for(inst["change"])
    return wrap(node.get("label", ""), limit), None, None


def diagram_svg(theme, instruments):
    """Layered top-to-bottom graph. Arrows carry numbered badges (edge order), not sentences."""
    nodes = {n["id"]: n for n in theme["nodes"]}
    rows = layers(theme)
    box = {}
    out = [f'<defs><marker id="mw-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
           f'markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{ACCENT}"/></marker></defs>']
    shapes = []
    y = 4
    for row in rows:
        width = _BOX_W.get(len(row), 104)
        total = width * len(row) + _GAP_X * (len(row) - 1)
        x = (W - total) / 2
        drawn = []
        for nid in row:
            names, change, colour = _node_lines(nodes[nid], width, instruments)
            height = len(names) * _LINE + (18 if change else 0) + 16
            drawn.append((nid, x, width, height, names, change, colour))
            x += width + _GAP_X
        row_h = max(d[3] for d in drawn)
        for nid, bx, bw, bh, names, change, colour in drawn:
            kind = nodes[nid].get("type")
            fill, stroke, ink = ((SOFT, ACCENT, INK) if kind == "event" else
                                 (INK, INK, "#ffffff") if kind == "mechanism" else ("#ffffff", colour, INK))
            box[nid] = (bx, y, bw, bh)
            shapes.append(f'<rect x="{bx:.1f}" y="{y}" width="{bw}" height="{bh}" rx="8" fill="{fill}" '
                          f'stroke="{stroke}" stroke-width="1.5"/>')
            ty = y + 8 + 12
            weight = ' font-weight="700"' if kind != "event" else ""
            for line in names:
                shapes.append(f'<text x="{bx + bw / 2:.1f}" y="{ty}" font-size="12.5" text-anchor="middle" '
                              f'fill="{ink}"{weight}>{esc(line)}</text>')
                ty += _LINE
            if change:
                shapes.append(f'<text x="{bx + bw / 2:.1f}" y="{ty + 2}" font-size="13" text-anchor="middle" '
                              f'fill="{colour}" font-weight="700">{esc(change)}</text>')
        y += row_h + _GAP_Y
    height = y - _GAP_Y + 4

    arrows, badges = [], []
    for k, edge in enumerate(theme["edges"], 1):
        ax, ay, aw, ah = box[edge["from"]]
        bx, by, bw, _ = box[edge["to"]]
        x1, y1, x2, y2 = ax + aw / 2, ay + ah, bx + bw / 2, by - 2
        arrows.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{ACCENT}" '
                      f'stroke-width="1.5" marker-end="url(#mw-arrow)"/>')
        mx, my = x1 + (x2 - x1) * 0.55, y1 + (y2 - y1) * 0.55
        badges.append(f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="9" fill="#ffffff" stroke="{ACCENT}" stroke-width="1.5"/>'
                      f'<text x="{mx:.1f}" y="{my + 3.5:.1f}" font-size="10.5" font-weight="700" '
                      f'text-anchor="middle" fill="{ACCENT}">{k}</text>')
    return _svg(height, f"{theme.get('title', '')}のつながりの図", "".join(out + arrows + shapes + badges))
