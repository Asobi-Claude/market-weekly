"""Validate work/issue.json (the explanations Claude wrote) before anything is published.

Usage: python scripts/issue.py validate [--snapshot work/snapshot.json] [--issue work/issue.json]
Prints `ok` and exits 0, or prints one problem per line and exits 1.
"""
import argparse
import json
import os
import sys
import urllib.parse
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = os.path.join(ROOT, "config", "sources.json")
NODE_TYPES = ("event", "mechanism", "instrument")
TOP_RANK = 10
MUST_INCLUDE_RANK = 3


def _s(value):
    return value.strip() if isinstance(value, str) else ""


def _l(value):
    return value if isinstance(value, list) else []


def _dicts(value):
    return [v for v in _l(value) if isinstance(v, dict)]


def _key(value):
    return value if isinstance(value, str) else None


def host_allowed(url, allowed):
    if not isinstance(url, str):
        return False
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        return False
    if parts.scheme != "https" or not host:
        return False
    if any(host == d or host.endswith("." + d) for d in allowed.get("domains", [])):
        return True
    return any(host.endswith(suffix) for suffix in allowed.get("suffixes", []))


def _featured_all(issue):
    ids = []
    for theme in _dicts(issue.get("themes")):
        for node in _dicts(theme.get("nodes")):
            if node.get("type") == "instrument" and _key(node.get("instrument")):
                ids.append(node["instrument"])
    for item in _dicts(issue.get("others")):
        if _key(item.get("instrument")):
            ids.append(item["instrument"])
    return ids


def featured_ids(issue):
    """Instrument ids the issue covers, in order of appearance, without repeats."""
    return list(dict.fromkeys(_featured_all(issue)))


def layers(theme):
    """Node ids grouped by depth (longest path from a root). Raises ValueError on a cycle."""
    ids = [n["id"] for n in _dicts(theme.get("nodes")) if _key(n.get("id"))]
    ids = list(dict.fromkeys(ids))
    known = set(ids)
    edges = [(e.get("from"), e.get("to")) for e in _dicts(theme.get("edges"))]
    edges = [(a, b) for a, b in edges if _key(a) in known and _key(b) in known]
    indegree = Counter(b for _, b in edges)
    depth = {i: 0 for i in ids}
    ready = [i for i in ids if not indegree[i]]
    done = 0
    while ready:
        node = ready.pop()
        done += 1
        for a, b in edges:
            if a == node:
                depth[b] = max(depth[b], depth[node] + 1)
                indegree[b] -= 1
                if not indegree[b]:
                    ready.append(b)
    if done != len(ids):
        raise ValueError("cycle in theme graph")
    out = [[] for _ in range(max(depth.values(), default=-1) + 1)]
    for i in ids:
        out[depth[i]].append(i)
    return out


def _check_theme(theme, where, inst, errs, used):
    if not _s(theme.get("title")):
        errs.append(f"{where}: title が空です")
    if not _s(theme.get("summary")):
        errs.append(f"{where}: summary が空です")

    nodes = _dicts(theme.get("nodes"))
    if len(nodes) != len(_l(theme.get("nodes"))) or not 3 <= len(nodes) <= 9:
        errs.append(f"{where}: nodes は 3〜9 個のオブジェクトにしてください")
    ids = [_key(n.get("id")) for n in nodes]
    for dup, count in Counter(i for i in ids if i).items():
        if count > 1:
            errs.append(f"{where}: ノード id「{dup}」が重複しています")
    theme_instruments = set()
    for n in nodes:
        nid = _key(n.get("id")) or "?"
        if not _s(n.get("id")):
            errs.append(f"{where}: id のないノードがあります")
        kind = n.get("type")
        if kind not in NODE_TYPES:
            errs.append(f"{where} ノード {nid}: type は event / mechanism / instrument のいずれかにしてください")
        elif kind == "instrument":
            if _key(n.get("instrument")) not in inst:
                errs.append(f"{where} ノード {nid}: 商品「{n.get('instrument')}」は snapshot にありません")
            else:
                theme_instruments.add(n["instrument"])
        else:
            if not _s(n.get("label")):
                errs.append(f"{where} ノード {nid}: label が空です")
            if kind == "event":
                refs = [r for r in _l(n.get("sources")) if _key(r)]
                used.update(refs)
                if not refs:
                    errs.append(f"{where} ノード {nid}: 出来事（event）には出典が1件以上必要です")
    types = [n.get("type") for n in nodes]
    if "event" not in types:
        errs.append(f"{where}: event ノードが1個以上必要です")
    if "instrument" not in types:
        errs.append(f"{where}: instrument ノードが1個以上必要です")

    known = {i for i in ids if i}
    edges = _dicts(theme.get("edges"))
    if len(edges) != len(_l(theme.get("edges"))):
        errs.append(f"{where}: edges はオブジェクトの配列にしてください")
    incoming = set()
    for k, e in enumerate(edges, 1):
        ew = f"{where} 矢印{k}"
        for end in ("from", "to"):
            if _key(e.get(end)) not in known:
                errs.append(f"{ew}: {end}「{e.get(end)}」というノードはありません")
        if _key(e.get("to")):
            incoming.add(e["to"])
        if not 1 <= len(_s(e.get("short"))) <= 24:
            errs.append(f"{ew}: short は 1〜24 字にしてください")
        if len(_s(e.get("explain"))) < 40:
            errs.append(f"{ew}: explain は 40 字以上で、仕組みから説明してください")
        used.update(r for r in _l(e.get("sources")) if _key(r))
    for n in nodes:
        nid = _key(n.get("id"))
        if nid and n.get("type") in ("mechanism", "instrument") and nid not in incoming:
            errs.append(f"{where} ノード {nid}: 入ってくる矢印がありません")
    try:
        if any(len(row) > 3 for row in layers(theme)):
            errs.append(f"{where}: 図の1段に並べられるノードは 3 個までです")
    except ValueError:
        errs.append(f"{where}: 矢印が循環しています")

    for g in _l(theme.get("glossary")):
        if not isinstance(g, dict) or not _s(g.get("term")) or not _s(g.get("text")):
            errs.append(f"{where}: glossary の各項目には term と text が必要です")

    focus = _dicts(theme.get("focus"))
    if len(focus) != len(_l(theme.get("focus"))) or not 1 <= len(focus) <= 3:
        errs.append(f"{where}: focus は 1〜3 件にしてください")
    for f in focus:
        fid = _key(f.get("instrument"))
        if fid not in theme_instruments:
            errs.append(f"{where}: focus の商品「{f.get('instrument')}」はこのテーマの instrument ノードにありません")
            continue
        days = {d for d, _ in inst[fid]["daily"]}
        for note in _l(f.get("notes")):
            if not isinstance(note, dict) or not _s(note.get("text")):
                errs.append(f"{where}: focus {fid} の notes には date と text が必要です")
            elif note.get("date") not in days:
                errs.append(f"{where}: focus {fid} の注記の日付 {note.get('date')} は値動きデータにありません")


def _check_other(item, where, inst, errs, used):
    if _key(item.get("instrument")) not in inst:
        errs.append(f"{where}: 商品「{item.get('instrument')}」は snapshot にありません")
    if not _s(item.get("what")):
        errs.append(f"{where}: what が空です")
    steps = _l(item.get("why_steps"))
    if any(not _s(step) for step in steps):
        errs.append(f"{where}: why_steps に空の段階があります")
    refs = [r for r in _l(item.get("sources")) if _key(r)]
    used.update(refs)
    if item.get("unclear") is True:
        return
    if not 2 <= len(steps) <= 5:
        errs.append(f"{where}: why_steps は 2〜5 段階にしてください（理由が不明なら unclear を true に）")
    if not refs:
        errs.append(f"{where}: 出典が1件以上必要です（理由が不明なら unclear を true に）")


def validate(issue, snapshot, allowed):
    """Return a list of problems (in Japanese). Empty means the issue may be published."""
    if not isinstance(issue, dict):
        return ["issue.json の最上位はオブジェクトにしてください"]
    errs = []
    inst = {i["id"]: i for i in snapshot["instruments"]}
    used = set()

    if issue.get("week_end") != snapshot["week_end"]:
        errs.append(f"week_end が snapshot（{snapshot['week_end']}）と一致しません")
    if not 1 <= len(_s(issue.get("headline"))) <= 40:
        errs.append("headline は 1〜40 字にしてください")
    if not _s(issue.get("quiz")):
        errs.append("quiz が空です")

    themes = _dicts(issue.get("themes"))
    if not isinstance(issue.get("themes"), list) or len(themes) != len(issue["themes"]) or len(themes) > 2:
        errs.append("themes は 0〜2 個のオブジェクトの配列にしてください")
    for k, theme in enumerate(themes, 1):
        _check_theme(theme, f"テーマ{k}", inst, errs, used)

    others = _dicts(issue.get("others"))
    if not isinstance(issue.get("others"), list) or len(others) != len(issue["others"]):
        errs.append("others はオブジェクトの配列にしてください")
    for k, item in enumerate(others, 1):
        _check_other(item, f"others {k}", inst, errs, used)
    if not themes and len(others) < 5:
        errs.append("themes が空のときは others を 5 個以上にしてください")

    every = _featured_all(issue)
    for id_, count in Counter(every).items():
        if count > 1:
            errs.append(f"商品「{id_}」が2回以上出ています。1か所にまとめてください")
    featured = featured_ids(issue)
    if not 5 <= len(featured) <= 7:
        errs.append(f"取り上げる商品は 5〜7 個にしてください（現在 {len(featured)} 個）")
    for id_ in featured:
        if id_ in inst and inst[id_]["rank"] > TOP_RANK:
            errs.append(f"商品「{id_}」は {inst[id_]['rank']} 位です。{TOP_RANK}位以内から選んでください")
    for i in snapshot["instruments"]:
        if i["rank"] <= MUST_INCLUDE_RANK and i["id"] not in featured:
            errs.append(f"{i['rank']} 位の「{i['id']}」は必ず取り上げてください")

    sources = _dicts(issue.get("sources"))
    if not isinstance(issue.get("sources"), list) or len(sources) != len(issue["sources"]):
        errs.append("sources はオブジェクトの配列にしてください")
    known = set()
    for src in sources:
        sid = _key(src.get("id"))
        if not _s(src.get("id")):
            errs.append("sources: id のない出典があります")
            continue
        if sid in known:
            errs.append(f"出典 id「{sid}」が重複しています")
        known.add(sid)
        for field in ("publisher", "title"):
            if not _s(src.get(field)):
                errs.append(f"出典 {sid}: {field} が空です")
        if not host_allowed(src.get("url"), allowed):
            errs.append(f"出典 {sid}: URL {src.get('url')} は許可された情報源（https）ではありません")
    for ref in sorted(used - known):
        errs.append(f"出典 id「{ref}」が sources にありません")
    for ref in sorted(known - used):
        errs.append(f"出典「{ref}」はどこからも参照されていません")
    return errs


def load_allowed(path=SOURCES):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--snapshot", default=os.path.join(ROOT, "work", "snapshot.json"))
    v.add_argument("--issue", default=os.path.join(ROOT, "work", "issue.json"))
    a = p.parse_args(argv)
    with open(a.snapshot, encoding="utf-8") as f:
        snapshot = json.load(f)
    try:
        with open(a.issue, encoding="utf-8") as f:
            issue = json.load(f)
    except (OSError, ValueError) as e:
        print(f"issue.json を読めません: {e}")
        return 1
    errs = validate(issue, snapshot, load_allowed())
    if errs:
        print("\n".join(errs))
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
