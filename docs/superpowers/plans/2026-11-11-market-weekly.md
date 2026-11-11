# 週刊 世界マーケット解説 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 毎週土曜8:00 JSTに、世界の主要金融商品の週間の値動きとその理由を図表入りWebページにして公開し、LINEでリンクを通知する。

**Architecture:** Claude Code ルーティンが `prompts/weekly.md` に従って動く。数字・選定・図・HTMLはすべて Python スクリプトが決定的に作り、Claude が書くのは「理由の調査結果と解説」を収めた `work/issue.json` だけ。その JSON は検証スクリプト（出典必須・許可ドメインのみ）を通らないと公開されない。ページは同じリポジトリの `docs/` を GitHub Pages で配信する。

**Tech Stack:** Python 3.12 標準ライブラリのみ（`urllib`, `json`, `html`, `statistics`, `unittest`）。外部パッケージなし。価格データは Yahoo Finance の chart API（無料・非公式）。GitHub Pages。LINE Messaging API。旬LINE（`C:\Users\Hiraku\shun-line`）と同じ流儀。

**Spec:** `docs/superpowers/specs/2026-11-11-market-weekly-design.md`（モックアップ: 同フォルダの `mockup-report-layouts.html` の右側 B案）

## Global Constraints

- 追加費用ゼロ。外部パッケージを入れない
- 騰落の数字は価格データからスクリプトが計算した値だけを表示する。`issue.json` に数値の騰落率を書く欄は作らない
- 理由の出典は `config/sources.json` の許可ドメインのみ。https のみ
- 理由が不明な値動きは `unclear: true` として正直に表示できること
- 毎号、騰落一覧グラフ・つながりの図（テーマがある号）・値動きの折れ線グラフが入る。文字だけの号は検証で落とす
- 取り上げる商品は 5〜7 個
- 「1週間」= 前週の最終営業日の終値 → 今週の最終営業日の終値。週の締め日は金曜（`week_end`）
- 値上がり `#c8372d`（赤）＋▲、値下がり `#2563a8`（青）＋▼。色だけに頼らない
- 日本語、スマホ優先（幅 360px で横スクロールなし）
- Claude が書いた文字列は HTML に埋め込む前に必ず `html.escape` する
- 秘密情報（`LINE_CHANNEL_ACCESS_TOKEN`, `LINE_USER_ID`）はリポジトリに置かない
- 同じ週に LINE を2回送らない
- 売買の推奨・今後の予想を書かない（プロンプトで禁止）
- ローカルの Python: `C:\Users\Hiraku\AppData\Local\Programs\Python\Python312\python.exe`（以下 `PY`）。ルーティン内は `python3`
- テスト実行: `PY -m unittest -v`（リポジトリ直下で）
- デフォルトブランチは `master`

## Review Focus

1. **金曜が休場の週・丸1週間休場の商品**（祝日、年末年始）→ その週の最後の営業日を使う。週内に営業日が1日もない商品は「データなし」として外し、落ちない（Task 3 のテスト）
2. **Yahoo が null の終値・空データ・HTTP エラーを返す** → その商品だけ外れ、他は続行。有効な商品が 10 未満なら休刊（Task 2・3 のテスト）
3. **Claude が書いた文章に `<`, `&`, `"` や `<script>` が含まれる** → そのまま文字として表示され、タグとして解釈されない（Task 5・6 のテスト）
4. **許可ドメインに似せた URL**（`reuters.com.evil.example`, `notreuters.com`, `http://`）→ 検証で拒否（Task 4 のテスト）
5. **同じ週の再実行**（手動実行の後に定期実行が走る）→ LINE は2通目が出ず、バックナンバー一覧に重複が出ない（Task 1・6・7 のテスト）

---

## File Structure

```
config/watchlist.json     監視リスト（id, 名前, Yahooシンボル, 種類）
config/sources.json       出典の許可ドメイン
config/site.json          {"base_url": "https://asobi-claude.github.io/market-weekly"}
scripts/state.py          週の締め日の計算、配信履歴 issues.json
scripts/prices.py         Yahoo から日足終値を取得・解析
scripts/weekly.py         週間騰落・普段比スコア・順位づけ → work/snapshot.json
scripts/issue.py          Claude が書いた work/issue.json の検証
scripts/charts.py         SVG（騰落一覧・折れ線・つながりの図）
scripts/render.py         HTML ページ・バックナンバー一覧・LINE通知文の生成
scripts/send_line.py      LINE 送信（旬LINEから移植）
scripts/wait_live.py      公開URLが見えるまで待つ
prompts/weekly.md         ルーティンの手順書
issues.json               配信履歴
data/<week_end>/          その号の snapshot.json と issue.json（再現用・一覧の元）
docs/issues/<week_end>.html, docs/index.html, docs/.nojekyll   公開ページ
work/                     作業用（.gitignore）
tests/test_*.py
```

---

### Task 1: リポジトリの土台と配信履歴（state.py）

**Files:**
- Create: `.gitignore`（`work/`, `__pycache__/`, `*.pyc`）, `scripts/__init__.py`, `tests/__init__.py`, `issues.json`（`[]`）, `docs/.nojekyll`（空）, `config/site.json`
- Create: `scripts/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Produces:
  - `today_jst(now: datetime | None = None) -> date`
  - `week_end_for(today: date) -> date` — `today` より**前**の直近の金曜
  - `load(path) -> list[dict]`, `save(path, entries)`（UTF-8, indent=2, 末尾改行。旬LINE `history.py` と同じ）
  - `is_done(entries, week_end: str) -> bool` — その週に `status` が `sent` か `skipped` の記録がある
  - `record(entries, *, week_end, status, headline=None, url=None, error=None) -> list[dict]` — 同じ `week_end` の既存記録は置き換える（重複させない）。`status` は `sent|skipped|failed`
  - CLI: `state.py status` → `{"today","week_end","already_done"}` を JSON 出力 / `state.py record --week-end D --status S [--headline H] [--url U] [--error E]`

- [ ] **Step 1: `git init -b master` し、土台ファイルを作る**

- [ ] **Step 2: 失敗するテストを書く**

```python
def test_week_end_is_last_friday_strictly_before_today(self):
    self.assertEqual(week_end_for(date(2026, 11, 14)), date(2026, 11, 13))  # 土
    self.assertEqual(week_end_for(date(2026, 11, 13)), date(2026, 11, 6))   # 金曜当日は前週
    self.assertEqual(week_end_for(date(2026, 11, 16)), date(2026, 11, 13))  # 月

def test_today_jst_crosses_midnight(self):
    self.assertEqual(today_jst(datetime(2026, 11, 13, 23, 0, tzinfo=timezone.utc)), date(2026, 11, 14))

def test_is_done_for_sent_and_skipped_but_not_failed(self):
    e = record([], week_end="2026-11-13", status="failed", error="x")
    self.assertFalse(is_done(e, "2026-11-13"))
    self.assertTrue(is_done(record(e, week_end="2026-11-13", status="sent", headline="h", url="u"), "2026-11-13"))
    self.assertTrue(is_done(record([], week_end="2026-11-13", status="skipped"), "2026-11-13"))

def test_record_replaces_same_week(self):  # Review Focus 5
    e = record([], week_end="2026-11-13", status="failed", error="x")
    e = record(e, week_end="2026-11-13", status="sent", headline="h", url="u")
    self.assertEqual(len(e), 1)
    self.assertNotIn("error", e[0])

def test_load_missing_or_empty_file_is_empty_list(self): ...
```

- [ ] **Step 3: `PY -m unittest tests.test_state -v` → FAIL（import エラー）を確認**
- [ ] **Step 4: `scripts/state.py` を実装**
- [ ] **Step 5: テストが PASS することを確認**
- [ ] **Step 6: Commit** `chore: scaffold and weekly state helpers`（spec・plan・mockup も一緒に）

---

### Task 2: 価格データの取得（prices.py）と監視リスト

**Files:**
- Create: `scripts/prices.py`, `config/watchlist.json`
- Test: `tests/test_prices.py`

**Interfaces:**
- Produces:
  - `class PriceError(Exception)`
  - `parse_chart(payload: dict) -> list[tuple[str, float]]` — `(現地日付 ISO, 終値)` を日付昇順で。終値 null の日は捨てる。同じ日付が複数あれば最後を採用。現地日付 = `timestamp + meta.gmtoffset` の日付
  - `fetch_series(symbol: str, opener=urllib.request.urlopen) -> list[tuple[str, float]]` — URL `https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=1y&interval=1d`、ヘッダ `User-Agent: Mozilla/5.0`、timeout 20。HTTP エラー・タイムアウト・JSON 不正・`chart.result` なし・結果が空は `PriceError`
  - CLI: `prices.py check` — 監視リスト全件を取得し `id シンボル 最終日 終値` または `id NG 理由` を表示

- `config/watchlist.json` は次の形の配列。`kind` は `price`（騰落率 %）か `yield`（利回りの変化幅）:

```json
[
 {"id":"sp500","name":"米国株 S&P500","symbol":"^GSPC","kind":"price","group":"株"},
 {"id":"nasdaq","name":"米国株 ナスダック","symbol":"^IXIC","kind":"price","group":"株"},
 {"id":"stoxx600","name":"欧州株 STOXX600","symbol":"^STOXX","kind":"price","group":"株"},
 {"id":"dax","name":"ドイツ株 DAX","symbol":"^GDAXI","kind":"price","group":"株"},
 {"id":"ftse","name":"英国株 FTSE100","symbol":"^FTSE","kind":"price","group":"株"},
 {"id":"nikkei","name":"日経平均","symbol":"^N225","kind":"price","group":"株"},
 {"id":"hangseng","name":"香港株 ハンセン","symbol":"^HSI","kind":"price","group":"株"},
 {"id":"shanghai","name":"中国株 上海総合","symbol":"000001.SS","kind":"price","group":"株"},
 {"id":"nifty","name":"インド株 Nifty50","symbol":"^NSEI","kind":"price","group":"株"},
 {"id":"em","name":"新興国株（ETF）","symbol":"EEM","kind":"price","group":"株"},
 {"id":"gold","name":"金","symbol":"GC=F","kind":"price","group":"商品"},
 {"id":"wti","name":"原油 WTI","symbol":"CL=F","kind":"price","group":"商品"},
 {"id":"copper","name":"銅","symbol":"HG=F","kind":"price","group":"商品"},
 {"id":"usdjpy","name":"ドル/円","symbol":"JPY=X","kind":"price","group":"為替"},
 {"id":"eurusd","name":"ユーロ/ドル","symbol":"EURUSD=X","kind":"price","group":"為替"},
 {"id":"dxy","name":"ドル指数","symbol":"DX-Y.NYB","kind":"price","group":"為替"},
 {"id":"us10y","name":"米国10年国債利回り","symbol":"^TNX","kind":"yield","group":"金利"},
 {"id":"btc","name":"ビットコイン","symbol":"BTC-USD","kind":"price","group":"その他"}
]
```

- [ ] **Step 1: 失敗するテストを書く**（`payload` は手書きの最小 fixture。`opener` は偽物を渡す）

```python
def test_parse_uses_exchange_local_date_and_skips_null(self):
    payload = {"chart": {"result": [{"meta": {"gmtoffset": 32400},
        "timestamp": [1794268800, 1794355200, 1794441600],   # 連続3日 00:00 UTC
        "indicators": {"quote": [{"close": [100.0, None, 103.5]}]}}]}}
    rows = parse_chart(payload)
    self.assertEqual([c for _, c in rows], [100.0, 103.5])          # Review Focus 2
    self.assertEqual(rows[0][0], date.fromtimestamp(1794268800 + 32400, timezone.utc).isoformat())

def test_parse_dedupes_same_date_keeping_last(self): ...
def test_parse_raises_on_missing_result(self):
    with self.assertRaises(PriceError): parse_chart({"chart": {"result": None, "error": {"code": "Not Found"}}})
def test_fetch_raises_price_error_on_http_error(self): ...   # opener が urllib.error.HTTPError(…404…) を投げる
def test_fetch_raises_price_error_on_timeout(self): ...      # opener が TimeoutError を投げる
def test_fetch_raises_on_empty_series(self): ...             # 終値がすべて null
def test_fetch_quotes_symbol_in_url(self): ...               # "^GSPC" → URL に "%5EGSPC"
```

- [ ] **Step 2: FAIL を確認 → Step 3: 実装 → Step 4: PASS を確認**
- [ ] **Step 5: 実データで確認** `PY scripts/prices.py check` を実行。18 件すべてが直近の営業日の終値を返すこと。NG のシンボルがあれば同じ対象の別シンボルに差し替え、代わりが無ければリストから外す（外したものは README の「監視リスト」に理由を書く）。日本10年国債利回りは Yahoo に信頼できる系列が無いため初版では入れない
- [ ] **Step 6: Commit** `feat: price fetching and watchlist`

---

### Task 3: 週間騰落・スコア・スナップショット（weekly.py）

**Files:**
- Create: `scripts/weekly.py`
- Test: `tests/test_weekly.py`

**Interfaces:**
- Consumes: `prices.fetch_series`, `prices.PriceError`, `state.week_end_for`, `state.today_jst`
- Produces:
  - `MIN_VALID = 10`, `LOOKBACK_WEEKS = 26`, `MIN_HISTORY_WEEKS = 8`
  - `last_close_in(series, after: date, upto: date) -> tuple[str, float] | None` — `after < 日付 <= upto` の最後の行
  - `weekly_change(series, week_end: date, kind: str) -> dict | None` — 終点 = `last_close_in(series, week_end-7日, week_end)`、始点 = `last_close_in(series, week_end-14日, week_end-7日)`。どちらか無ければ `None`。戻り値 `{"start_date","start","end_date","end","change","unit"}`。`kind=="price"`: `change=(end/start-1)*100`, `unit="%"`。`kind=="yield"`: `change=end-start`, `unit="pt"`
  - `score(series, week_end: date, kind: str) -> float | None` — `abs(今週の change) / median(abs(過去26週それぞれの change))`。過去の有効週が 8 未満、または中央値が 0 なら `None`
  - `build_snapshot(watchlist: list[dict], fetch, week_end: date) -> dict`

```json
{"week_end":"2026-11-13","week_start":"2026-11-09","status":"ok",
 "instruments":[{"id":"gold","name":"金","group":"商品","kind":"price","rank":1,"score":2.8,
   "change":3.2,"unit":"%","start_date":"2026-11-06","start":3900.0,"end_date":"2026-11-13","end":4024.8,
   "daily":[["2026-11-06",3900.0],["2026-11-09",3911.0]]}],
 "missing":[{"id":"shanghai","reason":"no trading day in week"}]}
```

  `instruments` は `score` 降順で `rank` 1 始まり。`daily` は始点の行から終点の行まで。`week_start` = `week_end - 4日`（月曜）。取得失敗・`weekly_change` が None・`score` が None の商品は `missing` へ。有効が `MIN_VALID` 未満なら `status: "insufficient"`
  - CLI: `weekly.py snapshot [--week-end YYYY-MM-DD] [--out work/snapshot.json]` — 省略時は `week_end_for(today_jst())`。`status` と上位10件を標準出力にも表示

- [ ] **Step 1: 失敗するテストを書く**（系列は「毎営業日の終値」を作るヘルパ `mk(start_date, closes)` で生成）

```python
def test_price_change_friday_to_friday(self):
    s = [("2026-11-06", 100.0), ("2026-11-09", 101.0), ("2026-11-13", 103.2)]
    c = weekly_change(s, date(2026, 11, 13), "price")
    self.assertAlmostEqual(c["change"], 3.2); self.assertEqual(c["unit"], "%")
    self.assertEqual((c["start_date"], c["end_date"]), ("2026-11-06", "2026-11-13"))

def test_yield_change_is_point_difference(self):
    c = weekly_change([("2026-11-06", 4.25), ("2026-11-13", 4.13)], date(2026, 11, 13), "yield")
    self.assertAlmostEqual(c["change"], -0.12); self.assertEqual(c["unit"], "pt")

def test_friday_holiday_uses_last_trading_day(self):            # Review Focus 1
    s = [("2026-11-06", 100.0), ("2026-11-12", 102.0)]           # 13日(金)休場
    self.assertEqual(weekly_change(s, date(2026, 11, 13), "price")["end_date"], "2026-11-12")

def test_whole_week_closed_returns_none(self):                   # Review Focus 1
    self.assertIsNone(weekly_change([("2026-11-06", 100.0)], date(2026, 11, 13), "price"))
def test_previous_week_closed_returns_none(self): ...
def test_saturday_bar_is_not_used(self):   # BTC: 11-14 の行があっても end_date は 11-13
def test_score_is_ratio_to_median_of_past_weeks(self): ...  # 過去は毎週±1%、今週3% → 3.0
def test_score_none_when_history_short(self): ...           # 過去7週しかない
def test_score_none_when_median_zero(self): ...             # 過去が全週横ばい（ゼロ除算しない）
def test_snapshot_ranks_by_score_and_collects_missing(self): # fetch が1銘柄で PriceError → missing に入り他は続行（Review Focus 2）
def test_snapshot_insufficient_when_fewer_than_min_valid(self):
```

- [ ] **Step 2: FAIL 確認 → Step 3: 実装 → Step 4: PASS 確認**
- [ ] **Step 5: 実データで確認** `PY scripts/weekly.py snapshot` を実行し、上位の騰落率を2〜3件、Yahoo Finance のサイト等の表示と見比べて一致を確認する
- [ ] **Step 6: Commit** `feat: weekly change, significance score, snapshot`

---

### Task 4: 解説データの検証（issue.py）

Claude が書く `work/issue.json` の形と、公開前に必ず通す検証。

**Files:**
- Create: `scripts/issue.py`, `config/sources.json`
- Test: `tests/test_issue.py`, `tests/fixtures.py`（有効な `snapshot` と `issue` を返す `sample_snapshot()`, `sample_issue()`。Task 5・6 でも使う）

**`issue.json` の形:**

```json
{
 "week_end": "2026-11-13",
 "headline": "「米国の利下げ観測」が世界を動かした",
 "themes": [{
   "title": "米国の利下げ観測",
   "summary": "2〜3文。何が起きて、何に波及したか。",
   "nodes": [
     {"id":"jobs","type":"event","label":"米雇用統計が予想を下回る","sources":["s1"]},
     {"id":"rates","type":"mechanism","label":"利下げ観測 → 米金利低下"},
     {"id":"n_gold","type":"instrument","instrument":"gold"}
   ],
   "edges": [
     {"from":"jobs","to":"rates","short":"景気を支えるため利下げへ","explain":"なぜそうなるのかを仕組みから。","sources":["s1"]},
     {"from":"rates","to":"n_gold","short":"利息のつかない金が相対的に魅力的に","explain":"…","sources":[]}
   ],
   "glossary": [{"term":"利下げ観測","text":"…"}],
   "focus": [{"instrument":"gold","notes":[{"date":"2026-11-11","text":"米雇用統計の発表"}]}]
 }],
 "others": [{"instrument":"wti","what":"何が起きたか（事実）","why_steps":["段階1","段階2"],"unclear":false,"sources":["s2"]}],
 "quiz": "説明してみよう の問い",
 "sources": [{"id":"s1","publisher":"ロイター","title":"記事名","url":"https://jp.reuters.com/..."}]
}
```

`config/sources.json`:

```json
{"domains": ["reuters.com","bloomberg.com","bloomberg.co.jp","nikkei.com","apnews.com","ft.com","wsj.com",
             "federalreserve.gov","boj.or.jp","ecb.europa.eu","bankofengland.co.uk"],
 "suffixes": [".gov",".go.jp",".gov.uk",".europa.eu"]}
```

**Interfaces:**
- Produces:
  - `host_allowed(url: str, allowed: dict) -> bool` — scheme が `https`、かつホストが `domains` のいずれかと一致またはそのサブドメイン、またはホストが `suffixes` のいずれかで終わる
  - `featured_ids(issue: dict) -> list[str]` — テーマの instrument ノードと `others` に出てくる商品 id（重複なし・登場順）
  - `layers(theme: dict) -> list[list[str]]` — ノード id を「根からの最長経路の深さ」で段に分けたもの。循環があれば `ValueError`
  - `validate(issue: dict, snapshot: dict, allowed: dict) -> list[str]` — 日本語のエラー文の一覧。空なら合格
  - CLI: `issue.py validate [--snapshot work/snapshot.json] [--issue work/issue.json]` — 合格なら `ok` で終了コード 0、不合格ならエラーを1行ずつ出して 1

**検証ルール（1ルール1テスト。`sample_issue()` を1か所壊して該当エラーが出ることを確認）:**

1. `week_end` が snapshot と一致
2. `headline` は 1〜40 字、`quiz` は空でない
3. `themes` は 0〜2 個
4. 取り上げる商品（`featured_ids`）は 5〜7 個、重複して別の場所に出ない、すべて snapshot の `rank` 10 位以内、`rank` 1〜3 位を必ず含む
5. テーマごと: ノード 3〜9 個・id 重複なし・`type` は `event|mechanism|instrument`・event と instrument が各1個以上・instrument ノードの `instrument` は snapshot に存在
6. テーマごと: エッジの `from`/`to` は存在するノード・循環なし・event 以外のノードには入ってくるエッジがある・1段に並ぶノードは 3 個まで
7. エッジごと: `short` は 1〜24 字、`explain` は 40 字以上
8. event ノードは `sources` が1件以上（事実には出典が必須）
9. テーマごと: `focus` は 1〜3 件、その `instrument` はそのテーマの instrument ノードにある、`notes[].date` は snapshot のその商品の `daily` に含まれる日付
10. `others` ごと: `instrument` は snapshot に存在、`what` は空でない。`unclear` が false なら `why_steps` 2〜5 個かつ `sources` 1件以上。true なら `why_steps` は空でもよい
11. `themes` が空なら `others` は 5 個以上
12. `sources`: id 重複なし、`publisher`・`title` が空でない、`url` は `host_allowed`
13. 参照されている出典 id はすべて `sources` に存在し、`sources` の各項目は少なくとも1か所から参照されている
14. `glossary` の各項目は `term`・`text` が空でない

- [ ] **Step 1: `tests/fixtures.py` を作る**（上の例を、商品 6 個・snapshot 12 件に膨らませた有効な組）
- [ ] **Step 2: 失敗するテストを書く** — `test_sample_is_valid`（エラー 0 件）、ルール 1〜14 それぞれの違反テスト、加えて:

```python
def test_host_allowed(self):                                    # Review Focus 4
    ok = lambda u: host_allowed(u, ALLOWED)
    self.assertTrue(ok("https://jp.reuters.com/markets/x"))
    self.assertTrue(ok("https://www.bls.gov/news.release/empsit.nr0.htm"))
    self.assertFalse(ok("http://www.reuters.com/x"))            # https 以外
    self.assertFalse(ok("https://reuters.com.evil.example/x"))
    self.assertFalse(ok("https://notreuters.com/x"))
    self.assertFalse(ok("https://example.com/?u=reuters.com"))
    self.assertFalse(ok("https://user@evil.example#.reuters.com"))
    self.assertFalse(ok("not a url"))

def test_validate_reports_all_errors_not_just_first(self): ...
def test_validate_does_not_crash_on_missing_keys(self):   # {} を渡しても例外でなくエラー一覧を返す
def test_all_others_mode_without_themes_is_valid(self):   # themes=[]、others 5個
```

- [ ] **Step 3: FAIL 確認 → Step 4: 実装 → Step 5: PASS 確認**
- [ ] **Step 6: Commit** `feat: issue schema validation with source allowlist`

---

### Task 5: 図表の SVG（charts.py）

**Files:**
- Create: `scripts/charts.py`
- Test: `tests/test_charts.py`

**Interfaces:**
- Consumes: `issue.layers`, `tests/fixtures.py`
- Produces（すべて `<svg viewBox=… width="100%" role="img" aria-label=…>` の文字列を返す。固定の viewBox 幅 340）:
  - `UP = "#c8372d"`, `DOWN = "#2563a8"`
  - `fmt_change(change: float, unit: str) -> str` — `"%"`: `▲3.2%` / `▼1.5%`（小数1桁）。`"pt"`: `▲0.12ポイント` / `▼0.12ポイント`（小数2桁）。丸めて 0 なら `±0.0%` / `±0.00ポイント`
  - `color_for(change: float) -> str`
  - `bars_svg(items: list[dict]) -> str` — 取り上げる商品の一覧。中央を 0 とする左右の横棒。棒の長さは `score` に比例（最大の score を全幅に）、ラベルは `name` と `fmt_change`。値上がりを上、値下がりを下に、それぞれ動きの大きい順
  - `line_svg(daily: list[list], notes: list[dict], change: float) -> str` — 折れ線。x 軸に `M/D`、`notes` の日付の点に丸印と注記文（長い注記は 16 字で折り返し、端で切れないよう左右寄せを切り替える）
  - `diagram_svg(theme: dict, instruments: dict[str, dict]) -> str` — `layers(theme)` の段を上から下へ。1段は最大3ノードを等間隔に。event は淡色の箱、mechanism は濃色の箱、instrument は白地に騰落色の枠で `name` と `fmt_change` を表示。ラベルは 10 字で折り返し。エッジは矢印で、**中点に番号バッジ（①②…、`edges` の並び順）** を置く。矢印の文章は図の中には書かない（解説リスト側で同じ番号を使う）

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_fmt_change(self):
    self.assertEqual(fmt_change(3.24, "%"), "▲3.2%")
    self.assertEqual(fmt_change(-1.46, "%"), "▼1.5%")
    self.assertEqual(fmt_change(-0.12, "pt"), "▼0.12ポイント")
    self.assertEqual(fmt_change(0.04, "%"), "±0.0%")

def test_each_svg_is_well_formed_xml(self):             # xml.etree.ElementTree.fromstring が通る
def test_bars_has_one_label_per_item_and_both_colors(self):
def test_diagram_has_one_badge_per_edge_and_one_box_per_node(self):
def test_diagram_shows_snapshot_change_for_instrument_nodes(self):   # "▲3.2%" が含まれる
def test_text_is_escaped(self):                         # Review Focus 3
    theme = sample_issue()["themes"][0]
    theme["nodes"][0]["label"] = '<script>alert(1)</script> & "x"'
    svg = diagram_svg(theme, INSTR)
    self.assertNotIn("<script>", svg); self.assertIn("&lt;script&gt;", svg)
    ET.fromstring(svg)
def test_line_handles_two_points_and_flat_series(self): # 終値がすべて同じでもゼロ除算しない
def test_line_note_on_first_and_last_day_stays_inside_viewbox(self):
```

- [ ] **Step 2: FAIL 確認 → Step 3: 実装 → Step 4: PASS 確認**
- [ ] **Step 5: 目で確認** `sample_snapshot()`/`sample_issue()` から3種の SVG を `work/preview-charts.html` に書き出すワンライナーを実行し、ブラウザで幅 360px にして、文字の重なり・はみ出しが無いことを確認する
- [ ] **Step 6: Commit** `feat: svg charts for bars, weekly line, and connection diagram`

---

### Task 6: ページ生成（render.py）

**Files:**
- Create: `scripts/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `charts.*`, `issue.featured_ids`, `tests/fixtures.py`, `config/site.json`
- Produces:
  - `render_issue(snapshot: dict, issue: dict) -> str` — 完全な HTML 文書（CSS はインライン、外部読み込みなし、`<meta name="viewport" content="width=device-width, initial-scale=1">`）
  - `render_index(items: list[dict]) -> str` — `items` は `{"week_end","headline"}`。新しい順に並べたバックナンバー一覧
  - `notice_text(snapshot, issue, url) -> str`
  - `issue_url(base_url, week_end) -> str` — `{base_url}/issues/{week_end}.html`
  - CLI: `render.py [--snapshot work/snapshot.json] [--issue work/issue.json]` — ① `docs/issues/<week_end>.html` を書く ② 入力2つを `data/<week_end>/` にコピー ③ `data/*/issue.json` を全部読んで `docs/index.html` を作り直す ④ `work/notice.txt` を書く ⑤ URL を標準出力に表示

**ページの構成（spec §3。見た目は mockup の B案の配色・余白を踏襲）:**

1. 題字「週刊 世界マーケット解説」と対象週（`11/9〜11/13の週`。`week_start`〜`week_end`）
2. 「今週の動き」: `bars_svg`（取り上げる商品のみ）と注記「棒の長さ＝普段の週と比べた動きの大きさ」
3. テーマごと: 濃色の帯に `title`・`summary` → 「つながりの図」`diagram_svg` → 「矢印を1本ずつ解説」番号つきで `short`（見出し）と `explain`、出典があれば `［出典: 発行元］` のリンク → `focus` の商品ごとに `line_svg` → 用語メモ
4. 「テーマ以外の大きな動き」（`themes` が空なら見出しは「今週の大きな動き」）: `others` を1件ずつカードで。商品名と `fmt_change`、`line_svg`（注記なし）、「何が起きた」`what`、「なぜ動いたか」`why_steps` を ▼ でつないだ段階図、出典。`unclear` のときは段階図の代わりに「はっきりした理由は報じられていません。」と表示
5. 「説明してみよう」`quiz`
6. 「出典」全 `sources` を `発行元｜記事名` のリンクで（`target="_blank" rel="noopener"`）
7. フッター: 「値動きは各市場の終値から計算。理由は報道にもとづく解釈を含みます。投資の勧誘・助言ではありません。」とバックナンバーへのリンク（`../index.html`）

**LINE 通知文（3行）:**

```
📈 週刊 世界マーケット解説（11/9〜11/13の週）
<headline>
<url>
```

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_page_contains_every_required_section(self):   # 上の 1〜7 の見出しと、svg が3つ以上（文字だけにならない）
def test_changes_come_from_snapshot(self):             # snapshot の change を書き換えると表示が変わる
def test_every_edge_explain_and_every_source_url_appears(self):
def test_user_text_is_escaped(self):                   # Review Focus 3
    issue = sample_issue(); issue["headline"] = '<img src=x onerror=alert(1)>'
    issue["themes"][0]["edges"][0]["explain"] = "a<b & c" * 10
    html_ = render_issue(sample_snapshot(), issue)
    self.assertNotIn("<img src=x", html_); self.assertIn("a&lt;b &amp; c", html_)
def test_unclear_item_shows_no_reason_text(self):
def test_no_theme_mode_renders_without_diagram(self):
def test_no_external_resources(self):                  # 出典リンク以外に http(s) の src/href/@import が無い
def test_index_lists_newest_first_and_links_relative(self):
def test_notice_is_three_lines_with_url(self):
def test_cli_rerun_same_week_keeps_single_index_entry(self):   # Review Focus 5。一時ディレクトリで2回実行
```

- [ ] **Step 2: FAIL 確認 → Step 3: 実装 → Step 4: PASS 確認**
- [ ] **Step 5: 目で確認** `sample_*` で `render_issue` した結果を `work/preview.html` に書き出してブラウザで開き、幅 360px で横スクロールが出ないこと、mockup B案と同じ読み心地であることを確認する
- [ ] **Step 6: Commit** `feat: issue page, back-number index, and LINE notice rendering`

---

### Task 7: LINE 送信と公開待ち（send_line.py, wait_live.py）

**Files:**
- Create: `scripts/send_line.py`（`C:\Users\Hiraku\shun-line\scripts\send_line.py` を移植）, `scripts/wait_live.py`
- Test: `tests/test_send_line.py`（旬LINEのテストを移植して下記に合わせる）, `tests/test_wait_live.py`

**Interfaces:**
- `send_line.py` の旬LINEからの変更点:
  - `--daily` を廃止し `--key <文字列>` に。CLI: `send_line.py [--key K] <message_file>`
  - `retry_key_for(key) = str(uuid.uuid5(uuid.NAMESPACE_URL, f"market-weekly/{key}"))`
  - `send(text, token, user_id, opener=…, retry_key=None)`、409 を成功扱い、トークンの伏せ字、`SendError` はそのまま
- `wait_live.py`:
  - `wait_until_live(url, *, opener=urllib.request.urlopen, sleep=time.sleep, attempts=30, interval=20) -> bool` — GET して 200 なら True。404 等や接続エラーは `sleep(interval)` して再試行。尽きたら False
  - CLI: `wait_live.py <url>` — `live` で 0、`timeout` で 1

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_retry_key_is_stable_per_week_and_differs_between_weeks(self):   # Review Focus 5
def test_409_with_key_is_treated_as_already_delivered(self):             # Review Focus 5
def test_error_detail_masks_token(self):
def test_wait_returns_true_after_404_then_200(self):   # 偽 opener と偽 sleep。sleep が1回呼ばれる
def test_wait_returns_false_when_never_live(self):     # attempts=3 → sleep 3回以下、False
def test_wait_survives_connection_error(self):
```

- [ ] **Step 2: FAIL 確認 → Step 3: 実装 → Step 4: PASS 確認**
- [ ] **Step 5: Commit** `feat: LINE sender with per-week idempotency and publish wait`

---

### Task 8: ルーティンの手順書・README・実データでの試作号

**Files:**
- Create: `prompts/weekly.md`, `README.md`

**`prompts/weekly.md` に書く手順（旬LINEの `prompts/daily.md` と同じ書き方で。この順番どおり）:**

1. `python3 scripts/state.py status`。`already_done` が true なら何もせず終了
2. `python3 scripts/weekly.py snapshot`。`status` が `insufficient` なら休刊: `work/notice.txt` に「週刊 世界マーケット解説：今週は価格データを取得できなかったため休刊です。」と書き、`send_line.py --key <week_end>` で送り、`state.py record --status skipped`、`issues.json` をコミットして push し終了
3. **商品を選ぶ**: `rank` 10 位以内から 5〜7 個。1〜3 位は必ず含める
4. **理由を調べる**: 商品ごとに Web 検索。使ってよいのは `config/sources.json` のドメインの記事だけ。記事を実際に開いて、その週のその値動きについて書かれていることを確かめる。記事に書かれていない理由は書かない。見つからない・見方が割れている場合は `unclear: true` にする
5. **構成を決める**: 複数の商品に共通する出来事があればテーマにする（最大2つ）。無理にこじつけない。共通点が無ければ `themes` を空にして全商品を `others` に
6. **`work/issue.json` を書く**（形は README の「issue.json の形」。数字の騰落率は書かない。`snapshot.json` にある値が自動で入る）。文章のルール:
   - 読者は「利下げ観測で金が買われた」だけでは腑に落ちない。`explain` と `why_steps` は「なぜそうなるのか」を仕組みから段階を追って書く
   - 専門用語は初出で噛み砕き、要のものは `glossary` に
   - 事実（発表・出来事）と解釈（「市場では〜と受け止められた」「〜と報じられている」）を書き分ける
   - 仕組みの説明は教科書的に定着した内容に限る
   - 売買の推奨、今後の値動きの予想は書かない
   - `quiz` はその号の因果を自分の言葉で説明させる問いを1つ
7. `python3 scripts/issue.py validate`。エラーが出たら `issue.json` を直して再実行（3回まで）。出典が足りないエラーを、検索せずに URL を作って埋めてはならない。通らなければ `state.py record --status failed --error …` を記録して push し、LINE は送らず終了
8. `python3 scripts/render.py`。表示された URL を控える
9. `docs/`, `data/` を `issue: <week_end> <headline>` でコミットし `master` に push（失敗時は `git pull --rebase origin master` して2回まで再試行）
10. `python3 scripts/wait_live.py <URL>`。`timeout` でも次へ進む
11. `python3 scripts/send_line.py --key <week_end> work/notice.txt`。失敗しても再送しない
12. `python3 scripts/state.py record --week-end … --status sent|failed --headline … --url …`、`issues.json` をコミットして push
13. 結果を1行で報告して終了

**`README.md`:** しくみ / issue.json の形（Task 4 の例と 14 ルール）/ 監視リストと出典ドメインの変え方 / 解説の深さ・長さの調整は `prompts/weekly.md` の手順6を書き換える / ルーティン設定表（下記）/ テストの実行方法

| 項目 | 設定 |
|---|---|
| リポジトリ | `Asobi-Claude/market-weekly`（公開） |
| スケジュール | `0 23 * * 5`（UTC）＝ 毎週土曜 8:00 JST |
| プロンプト | `prompts/weekly.md の手順に正確に従ってください。` |
| 環境変数 | `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_USER_ID`（旬LINEと同じ値） |
| ネットワーク | `api.line.me`, `query1.finance.yahoo.com`, `asobi-claude.github.io` と Web 検索・記事の閲覧を許可 |
| 権限 | `master` への push を許可 |

- [ ] **Step 1: `prompts/weekly.md` と `README.md` を書く**
- [ ] **Step 2: 実データで試作号を作る** — ローカルで手順 2〜8 を自分で実行する（直近の完了した週が対象。push と LINE 送信はしない）。検証が `ok` になり `docs/issues/<week_end>.html` ができること
- [ ] **Step 3: 全テスト** `PY -m unittest -v` → すべて PASS
- [ ] **Step 4: 本人に試作号を見てもらう** — ブラウザで開いて、数字の正しさ・出典・図表・解説の深さを確認してもらい、指摘は `prompts/weekly.md` またはテンプレートに反映する。**ここで本人の OK をもらうまで Task 9 に進まない**
- [ ] **Step 5: Commit** `docs: routine prompt and README`（試作号の `docs/issues/*`, `data/*` は、本人が初号として残すと言った場合だけコミットする。そうでなければ削除）

---

### Task 9: 公開と定期実行の設定（本人の確認が必要な操作）

外に向けた操作なので、各ステップの前に本人に確認する。

- [ ] **Step 1:** `gh repo create Asobi-Claude/market-weekly --public --source . --push`（公開リポジトリになることを伝えて確認。push 前に `git log -p` をトークンらしき文字列で検索し、秘密情報が入っていないことを確かめる）
- [ ] **Step 2:** GitHub Pages を有効化 — `gh api -X POST repos/Asobi-Claude/market-weekly/pages -f "source[branch]=master" -f "source[path]=/docs"`。`https://asobi-claude.github.io/market-weekly/` が開くこと、実際の URL が `config/site.json` の `base_url` と一致することを確認（違えば直してコミット）
- [ ] **Step 3:** ルーティンを作成（README の設定表のとおり。旬LINEのルーティンと同じ環境を使うか、同じ環境変数とネットワーク許可を持つ環境を用意）
- [ ] **Step 4:** ルーティンを手動で1回実行し、次を確認: Yahoo からクラウド環境で価格が取れる（`snapshot` が `ok`）／ページが公開される／LINE に通知が届きリンクがスマホで開く／`issues.json` が push される／もう一度手動実行しても2通目が来ない
- [ ] **Step 5:** クラウド環境から Yahoo が取得できなかった場合はここで止め、状況（HTTP ステータス）を本人に報告して、別の無料データ源への差し替えを相談する（差し替えは `scripts/prices.py` の `fetch_series` と `parse_chart` だけで済む）
- [ ] **Step 6:** メモリ `market-weekly-project.md` を稼働状況で更新する
