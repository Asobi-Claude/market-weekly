# 週刊 世界マーケット解説

毎週 **土曜 8:00（日本時間）** に、その週に大きく動いた世界の金融商品（株価指数・金・原油・為替・金利など）と、その値動きの理由を、図表入りのページにまとめて公開し、LINE でリンクを知らせるしくみです。

Claude Code のルーティン（クラウドでの定期実行）が `prompts/weekly.md` に従って動きます。

## しくみ

数字と図はすべてスクリプトが価格データから作ります。Claude が書くのは解説（`work/issue.json`）だけで、それも検証を通らないと公開されません。

| ファイル | 役割 |
|---|---|
| `prompts/weekly.md` | ルーティンが毎週従う手順書。**解説の深さ・長さ・トーンを変えたいときは、ここの手順 6 を書き換えます** |
| `config/watchlist.json` | 毎週チェックする商品の一覧（監視リスト） |
| `config/sources.json` | 理由の出典として認めるサイト |
| `config/site.json` | 公開ページの URL |
| `scripts/state.py` | 週の締め日（金曜）の計算と、配信の履歴 `issues.json` |
| `scripts/prices.py` | Yahoo Finance から日々の終値を取得 |
| `scripts/weekly.py` | 1 週間の騰落と「普段と比べた動きの大きさ」を計算し、順位を付ける → `work/snapshot.json` |
| `scripts/issue.py` | 解説 `work/issue.json` の検証 |
| `scripts/charts.py` | グラフと「つながりの図」（SVG） |
| `scripts/render.py` | ページ、バックナンバー一覧、LINE の通知文を作る |
| `scripts/send_line.py` | LINE への送信（同じ週に 2 通送らない） |
| `scripts/wait_live.py` | ページが公開されるまで待つ |
| `docs/` | 公開されるページ（GitHub Pages） |
| `data/<金曜の日付>/` | その号のもとになったデータ（再現用） |

### 値動きの決まり

- 「1 週間」＝ 前の週の最後の営業日の終値 → 今週の最後の営業日の終値。
- 株・商品・為替は騰落率（%）、金利は利回りの変化幅（ポイント）。
- 順位は騰落率の大きさではなく、**その商品の普段の週（過去 26 週の中央値）と比べて何倍動いたか**で付けます。
- 価格が取れなかった商品はその週は扱いません。取れた商品が 10 未満の週は休刊です。

### 出典として認めるサイト

`config/sources.json` にあるサイトだけです。日経、ブルームバーグ、時事、AFP、CNBC、NPR、PBS、ABC、CBS、NBC、ロイター、AP、FT、WSJ と、各国の中央銀行・政府（`.gov`、`.go.jp` など）。

Claude の Web 検索には制約があります（2026年11月に確認）。

- ロイター、AP、FT、WSJ、NHK、共同、BBC は検索できません（ロイターなど 4 つは、使えるようになったときのために一覧には残しています）。
- ブルームバーグは検索には出ますが、記事本文は開けません。見出しと要約での確認を認めています。
- 日経は開けます（会員限定の記事は冒頭だけ）。

### 監視リスト

世界の株価指数 10、商品 3、為替 3、金利 1、ビットコインの計 18 個です。`config/watchlist.json` を書き換えると変えられます（`symbol` は Yahoo Finance の記号）。変えたあとは `python scripts/prices.py check` で全部取れることを確かめます。

日本 10 年国債利回りと TOPIX は、Yahoo Finance に信頼できるデータがないため入れていません。

## issue.json の形

```json
{
 "week_end": "2026-11-13",
 "headline": "40字以内の見出し",
 "themes": [{
   "title": "テーマ名",
   "summary": "2〜3文。何が起きて、何に波及したか。",
   "nodes": [
     {"id": "jobs", "type": "event", "label": "米雇用統計が予想を下回る", "sources": ["s1"]},
     {"id": "rates", "type": "mechanism", "label": "利下げ観測 → 米金利低下"},
     {"id": "n_gold", "type": "instrument", "instrument": "gold"}
   ],
   "edges": [
     {"from": "jobs", "to": "rates", "short": "24字以内の見出し", "explain": "なぜそうなるのかを仕組みから（40字以上）", "sources": ["s1"]},
     {"from": "rates", "to": "n_gold", "short": "…", "explain": "…", "sources": []}
   ],
   "glossary": [{"term": "利下げ観測", "text": "…"}],
   "focus": [{"instrument": "gold", "notes": [{"date": "2026-11-11", "text": "米雇用統計の発表"}]}]
 }],
 "others": [
   {"instrument": "wti", "what": "何が起きたか（事実）", "why_steps": ["段階1", "段階2"], "unclear": false, "sources": ["s2"]}
 ],
 "quiz": "説明してみよう の問い",
 "sources": [{"id": "s1", "publisher": "ロイター", "title": "記事名", "url": "https://jp.reuters.com/..."}]
}
```

`instrument` には `work/snapshot.json` の商品の `id` を書きます。

### 検証の決まり（`python scripts/issue.py validate`）

1. `week_end` が snapshot と同じ
2. `headline` は 1〜40 字、`quiz` は空でない
3. `themes` は 0〜2 個
4. 取り上げる商品は 5〜7 個。同じ商品を 2 か所に出さない。すべて 10 位以内。1〜3 位は必ず含む
5. テーマのノードは 3〜9 個、id は重複なし、`type` は `event`（出来事）/ `mechanism`（仕組み）/ `instrument`（商品）。event と instrument が各 1 個以上
6. 矢印は存在するノード同士を結ぶ。循環しない。event 以外のノードには入ってくる矢印がある。図の 1 段に並ぶのは 3 個まで
7. 矢印の `short` は 1〜24 字、`explain` は 40 字以上
8. event には出典が 1 件以上
9. `focus` は 1〜3 件。そのテーマの商品で、注記の日付は値動きデータにある日
10. `others` は `what` が必須。`unclear` が false なら `why_steps` 2〜5 段階と出典 1 件以上
11. `themes` が空なら `others` は 5 個以上
12. 出典は id 重複なし、`publisher`・`title` あり、URL は `config/sources.json` のサイトの https
13. 参照した出典 id はすべて `sources` にあり、`sources` の各項目はどこかから参照されている
14. `glossary` の各項目は `term` と `text` がある

## 定期実行（Claude Code ルーティン）

| 項目 | 設定 |
|---|---|
| リポジトリ | `Asobi-Claude/market-weekly`（公開） |
| スケジュール | `0 23 * * 5`（UTC）＝ 毎週土曜 8:00 JST |
| プロンプト | `prompts/weekly.md の手順に正確に従ってください。` |
| 環境変数 | `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_USER_ID`（旬LINE と同じ値） |
| ネットワーク | `api.line.me`, `query1.finance.yahoo.com`, `asobi-claude.github.io` と、Web 検索・記事の閲覧を許可 |
| 権限 | `master` への push を許可 |

> トークンは秘密情報です。このリポジトリは公開なので、ファイルやコミットに絶対に入れないでください。

GitHub Pages は、リポジトリの Settings → Pages で「Deploy from a branch」、ブランチ `master`、フォルダ `/docs` に設定します。

## 手元で試す

PowerShell（`market-weekly` フォルダで）:

```powershell
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
& $py scripts\weekly.py snapshot          # 値動きを計算 → work\snapshot.json
# work\issue.json を用意してから
& $py scripts\issue.py validate           # 検証
& $py scripts\render.py                   # ページを作る → docs\issues\<日付>.html
```

## テスト

```
python -m unittest
```
