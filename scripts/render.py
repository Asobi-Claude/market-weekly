"""Build the weekly issue page, the back-number index, and the LINE notice.

Usage: python scripts/render.py [--snapshot work/snapshot.json] [--issue work/issue.json]
Writes docs/issues/<week_end>.html, data/<week_end>/, docs/index.html, work/notice.txt; prints the URL.
"""
import argparse
import glob
import json
import os
import sys
from datetime import date

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import charts  # noqa: E402
from scripts.charts import esc  # noqa: E402
from scripts.issue import featured_ids  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TITLE = "週刊 世界マーケット解説"

CSS = """
:root{--ink:#1c2230;--sub:#667085;--line:#e4e7ec;--paper:#fffdf9;--accent:#8a6d1f;--soft:#f6f1e3}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:"Hiragino Sans","Yu Gothic UI","Noto Sans JP","Meiryo",sans-serif;line-height:1.75;-webkit-text-size-adjust:100%}
main{max-width:560px;margin:0 auto;padding:18px 16px 40px}
svg{display:block;max-width:100%;height:auto}
svg text{font-family:inherit}
a{color:#1d4f91}
.mast{border-bottom:2px solid var(--ink);padding-bottom:8px;margin-bottom:14px}
.mast .t{font-family:"Hiragino Mincho ProN","Yu Mincho","Noto Serif JP",serif;font-size:22px;font-weight:700}
.mast .d{font-size:12.5px;color:var(--sub)}
h1{font-family:"Hiragino Mincho ProN","Yu Mincho","Noto Serif JP",serif;font-size:21px;line-height:1.5;margin:10px 0 16px}
h2{font-size:16px;margin:28px 0 8px}
h3{font-size:15px;margin:0 0 4px}
p{font-size:15px;margin:6px 0}
.lbl{font-size:11.5px;letter-spacing:.08em;color:var(--accent);font-weight:700;margin-top:12px}
.cap{font-size:12px;color:var(--sub);margin-top:4px}
.theme{background:var(--ink);color:#fff;border-radius:12px;padding:14px;margin-top:26px}
.theme .lbl{color:#e8c96a;margin-top:0}
.theme .big{font-family:"Hiragino Mincho ProN","Yu Mincho","Noto Serif JP",serif;font-size:19px;font-weight:700;line-height:1.5;margin-top:2px}
.theme p{font-size:14px;color:#dfe3ea}
.card{border:1px solid var(--line);border-radius:12px;padding:14px;margin-top:12px;background:#fff}
.head{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.name{font-size:17px;font-weight:700}
.chg{font-size:17px;font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}
.edge{display:grid;grid-template-columns:26px 1fr;gap:8px;padding:12px 0;border-top:1px solid var(--line)}
.edge:first-of-type{border-top:0}
.num{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border:1.5px solid var(--accent);border-radius:50%;color:var(--accent);font-size:12.5px;font-weight:700;margin-top:2px}
.src{font-size:12.5px;color:var(--sub)}
.chain{margin:8px 0}
.step{background:var(--soft);border-radius:8px;padding:8px 10px;font-size:14px}
.arrow{text-align:center;color:var(--accent);font-size:13px;line-height:1.3}
.memo{border-left:3px solid var(--accent);padding:6px 10px;font-size:13.5px;color:#4a4436;background:#fbf8ef;margin-top:10px}
.quiz{margin-top:8px;padding:12px;border:1px dashed #b9bfca;border-radius:8px;font-size:14.5px}
.unclear{font-size:14px;color:var(--sub);background:#f4f5f7;border-radius:8px;padding:8px 10px}
.sources{padding-left:18px;font-size:13px}
.sources li{margin:4px 0;overflow-wrap:anywhere}
footer{margin-top:32px;padding-top:12px;border-top:1px solid var(--line);font-size:12px;color:var(--sub)}
.list{list-style:none;padding:0}
.list li{border-bottom:1px solid var(--line);padding:12px 0}
.list a{font-size:16px;font-weight:700;text-decoration:none}
.list .d{font-size:12.5px;color:var(--sub)}
"""


def _md(iso):
    d = date.fromisoformat(iso)
    return f"{d.month}/{d.day}"


def week_label(snapshot):
    return f"{_md(snapshot['week_start'])}〜{_md(snapshot['week_end'])}の週"


def issue_url(base_url, week_end):
    return f"{base_url.rstrip('/')}/issues/{week_end}.html"


def notice_text(snapshot, issue, url):
    return f"📈 {TITLE}（{week_label(snapshot)}）\n{issue['headline']}\n{url}\n"


def _document(title, body):
    return ("<!DOCTYPE html>\n"
            f'<html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{esc(title)}</title><style>{CSS}</style></head>"
            f"<body><main>{body}</main></body></html>\n")


def _refs(ids, sources):
    links = [f'<a href="{esc(sources[i]["url"])}" target="_blank" rel="noopener">{esc(sources[i]["publisher"])}</a>'
             for i in ids if i in sources]
    return f'<div class="src">［出典: {"、".join(links)}］</div>' if links else ""


def _change_span(inst):
    return (f'<span class="chg" style="color:{charts.color_for(inst["change"])}">'
            f'{esc(charts.fmt_change(inst["change"], inst["unit"]))}</span>')


def _theme_html(theme, inst, sources):
    out = [f'<section><div class="theme"><div class="lbl">今週のテーマ</div>'
           f'<div class="big">{esc(theme["title"])}</div><p>{esc(theme["summary"])}</p></div>',
           "<h2>つながりの図</h2>", charts.diagram_svg(theme, inst),
           '<div class="cap">数字のついた矢印を、下で1本ずつ解説します。</div>',
           '<h2>矢印を1本ずつ解説</h2><div class="card">']
    nodes = {n["id"]: n for n in theme["nodes"]}

    def label(nid):
        node = nodes[nid]
        return inst[node["instrument"]]["name"] if node["type"] == "instrument" else node["label"]

    for k, edge in enumerate(theme["edges"], 1):
        out.append(f'<div class="edge"><span class="num">{k}</span><div>'
                   f'<div class="src">{esc(label(edge["from"]))} → {esc(label(edge["to"]))}</div>'
                   f'<h3>{esc(edge["short"])}</h3><p>{esc(edge["explain"])}</p>'
                   f'{_refs(edge.get("sources", []), sources)}</div></div>')
    out.append("</div>")
    events = [n for n in theme["nodes"] if n["type"] == "event"]
    if events:
        out.append('<div class="lbl">起きた出来事の出典</div>')
        out.extend(f'<p>{esc(n["label"])}</p>{_refs(n.get("sources", []), sources)}' for n in events)
    for focus in theme.get("focus", []):
        item = inst[focus["instrument"]]
        out.append(f'<div class="card"><div class="head"><span class="name">{esc(item["name"])}の1週間</span>'
                   f'{_change_span(item)}</div>'
                   f'{charts.line_svg(item["daily"], focus.get("notes", []), item["change"])}</div>')
    for g in theme.get("glossary", []):
        out.append(f'<div class="memo"><b>用語メモ｜{esc(g["term"])}</b><br>{esc(g["text"])}</div>')
    out.append("</section>")
    return "".join(out)


def _other_html(item, inst, sources):
    data = inst[item["instrument"]]
    out = [f'<div class="card"><div class="head"><span class="name">{esc(data["name"])}</span>{_change_span(data)}</div>',
           charts.line_svg(data["daily"], [], data["change"]),
           f'<div class="lbl">何が起きた</div><p>{esc(item["what"])}</p>', '<div class="lbl">なぜ動いたか</div>']
    if item.get("unclear"):
        out.append('<div class="unclear">はっきりした理由は報じられていません。</div>')
    steps = item.get("why_steps", [])
    if steps:
        chain = '<div class="arrow">▼</div>'.join(f'<div class="step">{esc(s)}</div>' for s in steps)
        out.append(f'<div class="chain">{chain}</div>')
    out.append(_refs(item.get("sources", []), sources))
    out.append("</div>")
    return "".join(out)


def render_issue(snapshot, issue):
    inst = {i["id"]: i for i in snapshot["instruments"]}
    sources = {s["id"]: s for s in issue["sources"]}
    featured = [inst[i] for i in featured_ids(issue)]
    themes, others = issue.get("themes", []), issue.get("others", [])
    out = [f'<div class="mast"><div class="t">{TITLE}</div><div class="d">{esc(week_label(snapshot))}</div></div>',
           f'<h1>{esc(issue["headline"])}</h1>',
           '<div class="lbl">今週の動き</div>', charts.bars_svg(featured),
           '<div class="cap">棒の長さ＝普段の週と比べた動きの大きさ。数字は1週間の変化。</div>']
    out.extend(_theme_html(t, inst, sources) for t in themes)
    if others:
        out.append(f'<h2>{"テーマ以外の大きな動き" if themes else "今週の大きな動き"}</h2>')
        out.extend(_other_html(o, inst, sources) for o in others)
    out.append(f'<h2>説明してみよう</h2><div class="quiz">{esc(issue["quiz"])}</div>')
    out.append('<h2>出典</h2><ul class="sources">')
    out.extend(f'<li><a href="{esc(s["url"])}" target="_blank" rel="noopener">{esc(s["publisher"])}｜{esc(s["title"])}</a></li>'
               for s in issue["sources"])
    out.append("</ul>")
    out.append('<footer>値動きは各市場の終値から計算。理由は報道にもとづく解釈を含みます。'
               '投資の勧誘・助言ではありません。<br><a href="../index.html">バックナンバー</a></footer>')
    return _document(f"{issue['headline']}｜{TITLE}", "".join(out))


def render_index(items):
    out = [f'<div class="mast"><div class="t">{TITLE}</div><div class="d">バックナンバー</div></div>']
    if not items:
        out.append("<p>まだ号がありません。</p>")
    else:
        out.append('<ul class="list">')
        for item in sorted(items, key=lambda i: i["week_end"], reverse=True):
            out.append(f'<li><div class="d">{esc(item["week_end"])} までの週</div>'
                       f'<a href="issues/{esc(item["week_end"])}.html">{esc(item["headline"])}</a></li>')
        out.append("</ul>")
    return _document(f"{TITLE}｜バックナンバー", "".join(out))


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def build(snapshot_path, issue_path, root=ROOT):
    snapshot, issue = _load(snapshot_path), _load(issue_path)
    week_end = date.fromisoformat(snapshot["week_end"]).isoformat()
    url = issue_url(_load(os.path.join(root, "config", "site.json"))["base_url"], week_end)

    _write(os.path.join(root, "docs", "issues", f"{week_end}.html"), render_issue(snapshot, issue))
    for name, obj in (("snapshot.json", snapshot), ("issue.json", issue)):
        _write(os.path.join(root, "data", week_end, name), json.dumps(obj, ensure_ascii=False, indent=1) + "\n")

    items = []
    for path in glob.glob(os.path.join(root, "data", "*", "issue.json")):
        items.append({"week_end": os.path.basename(os.path.dirname(path)),
                      "headline": str(_load(path).get("headline", ""))})
    _write(os.path.join(root, "docs", "index.html"), render_index(items))
    _write(os.path.join(root, "work", "notice.txt"), notice_text(snapshot, issue, url))
    return url


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot", default=os.path.join(ROOT, "work", "snapshot.json"))
    p.add_argument("--issue", default=os.path.join(ROOT, "work", "issue.json"))
    a = p.parse_args(argv)
    print(build(a.snapshot, a.issue))
    return 0


if __name__ == "__main__":
    sys.exit(main())
