"""A valid snapshot/issue pair shared by the issue, chart, and render tests. All values are made up."""
import copy

_DAYS = ["2026-11-06", "2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"]

_ROWS = [  # id, name, group, kind, change
    ("gold", "金", "商品", "price", 3.2),
    ("wti", "原油 WTI", "商品", "price", -4.4),
    ("nikkei", "日経平均", "株", "price", -2.1),
    ("usdjpy", "ドル/円", "為替", "price", -1.5),
    ("sp500", "米国株 S&P500", "株", "price", 1.8),
    ("us10y", "米国10年国債利回り", "金利", "yield", -0.12),
    ("dax", "ドイツ株 DAX", "株", "price", 0.9),
    ("nasdaq", "米国株 ナスダック", "株", "price", 1.1),
    ("copper", "銅", "商品", "price", -0.8),
    ("eurusd", "ユーロ/ドル", "為替", "price", 0.5),
    ("btc", "ビットコイン", "その他", "price", 0.7),
    ("ftse", "英国株 FTSE100", "株", "price", 0.2),
]


def _instrument(rank, id_, name, group, kind, change):
    start = 4.25 if kind == "yield" else 100.0
    end = start + change if kind == "yield" else start * (1 + change / 100)
    step = (end - start) / (len(_DAYS) - 1)
    return {"id": id_, "name": name, "group": group, "kind": kind, "rank": rank,
            "score": round(4.0 - 0.3 * (rank - 1), 2), "change": change,
            "unit": "pt" if kind == "yield" else "%",
            "start_date": _DAYS[0], "start": start, "end_date": _DAYS[-1], "end": end,
            "daily": [[d, start + step * i] for i, d in enumerate(_DAYS)]}


_SNAPSHOT = {
    "week_end": "2026-11-13", "week_start": "2026-11-09", "status": "ok",
    "instruments": [_instrument(i + 1, *row) for i, row in enumerate(_ROWS)],
    "missing": [],
}

_ISSUE = {
    "week_end": "2026-11-13",
    "headline": "「米国の利下げ観測」が世界を動かした",
    "themes": [{
        "title": "米国の利下げ観測",
        "summary": "弱い雇用統計をきっかけに、金・株・為替が同時に動きました。別々のニュースに見えて、根っこは1つです。",
        "nodes": [
            {"id": "jobs", "type": "event", "label": "米雇用統計が予想を下回る", "sources": ["s1"]},
            {"id": "rates", "type": "mechanism", "label": "利下げ観測 → 米金利低下"},
            {"id": "n_gold", "type": "instrument", "instrument": "gold"},
            {"id": "n_sp500", "type": "instrument", "instrument": "sp500"},
            {"id": "n_usdjpy", "type": "instrument", "instrument": "usdjpy"},
            {"id": "n_nikkei", "type": "instrument", "instrument": "nikkei"},
        ],
        "edges": [
            {"from": "jobs", "to": "rates", "short": "景気を支えるため利下げへ",
             "explain": "雇用が弱いと景気の先行きが心配されます。中央銀行は金利を下げてお金を借りやすくし、景気を支えようとします。",
             "sources": ["s1"]},
            {"from": "rates", "to": "n_gold", "short": "利息のつかない金が魅力的に",
             "explain": "金利が下がると預金や国債でもらえる利息が減ります。もともと利息がつかない金との差が縮まり、金が買われやすくなります。",
             "sources": []},
            {"from": "rates", "to": "n_sp500", "short": "企業がお金を借りやすくなる",
             "explain": "金利が下がると企業は低い利息でお金を借りて投資でき、利益が増えやすくなるという期待から株が買われます。",
             "sources": ["s2"]},
            {"from": "rates", "to": "n_usdjpy", "short": "ドルの利息が減りドル安に",
             "explain": "米国の金利が下がるとドルで持っていても得られる利息が減ります。ドルを売って他の通貨に替える人が増え、ドルが安くなります。",
             "sources": []},
            {"from": "n_usdjpy", "to": "n_nikkei", "short": "円高は輸出企業の利益を減らす",
             "explain": "日本の大企業は輸出で稼ぐ会社が多く、海外で稼いだドルを円に替えると目減りします。利益が減るという見方から株が売られました。",
             "sources": ["s2"]},
        ],
        "glossary": [{"term": "利下げ観測", "text": "まだ決まっていないが、市場が「そうなりそうだ」と予想している状態。"}],
        "focus": [{"instrument": "gold", "notes": [{"date": "2026-11-11", "text": "米雇用統計の発表"}]}],
    }],
    "others": [
        {"instrument": "wti", "what": "産油国が増産で合意したと報じられました。",
         "why_steps": ["産油国が生産量を増やす", "市場に出回る原油が増える見通しになる", "余りそうなものは値段が下がる"],
         "unclear": False, "sources": ["s3"]},
        {"instrument": "dax", "what": "週を通じて小幅に上昇しました。", "why_steps": [], "unclear": True, "sources": []},
    ],
    "quiz": "「米国の雇用が弱いと、なぜ日本株が下がることがあるのか」を3ステップで説明してみましょう。",
    "sources": [
        {"id": "s1", "publisher": "ロイター", "title": "米雇用統計、予想下回る", "url": "https://jp.reuters.com/markets/a1"},
        {"id": "s2", "publisher": "日本経済新聞", "title": "日経平均が反落", "url": "https://www.nikkei.com/article/b2"},
        {"id": "s3", "publisher": "Bloomberg", "title": "原油が下落", "url": "https://www.bloomberg.co.jp/news/c3"},
    ],
}

ALLOWED = {
    "domains": ["reuters.com", "bloomberg.com", "bloomberg.co.jp", "nikkei.com", "apnews.com", "ft.com", "wsj.com",
                "federalreserve.gov", "boj.or.jp", "ecb.europa.eu", "bankofengland.co.uk"],
    "suffixes": [".gov", ".go.jp", ".gov.uk", ".europa.eu"],
}


def sample_snapshot():
    return copy.deepcopy(_SNAPSHOT)


def sample_issue():
    return copy.deepcopy(_ISSUE)


def no_theme_issue():
    """Same week told instrument by instrument, with no shared theme."""
    issue = sample_issue()
    issue["themes"] = []
    issue["others"] = [
        {"instrument": id_, "what": f"{id_} が動きました。", "why_steps": ["段階その1", "段階その2"],
         "unclear": False, "sources": ["s1"]}
        for id_ in ("gold", "wti", "nikkei", "usdjpy", "sp500")
    ]
    issue["sources"] = issue["sources"][:1]
    return issue
