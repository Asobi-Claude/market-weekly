import json
import os
import re
import tempfile
import unittest

from scripts.render import (build, issue_url, notice_text, render_index,
                            render_issue, week_label)
from tests.fixtures import no_theme_issue, sample_issue, sample_snapshot

BASE = "https://example.github.io/market-weekly"


class IssuePageTest(unittest.TestCase):
    def setUp(self):
        self.snap, self.issue = sample_snapshot(), sample_issue()
        self.page = render_issue(self.snap, self.issue)

    def test_page_contains_every_required_section(self):
        self.assertTrue(self.page.startswith("<!DOCTYPE html>"))
        self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1">', self.page)
        self.assertIn('lang="ja"', self.page)
        for heading in ("週刊 世界マーケット解説", "11/9〜11/13の週", "今週の動き", "今週のテーマ", "つながりの図",
                        "矢印を1本ずつ解説", "テーマ以外の大きな動き", "説明してみよう", "出典",
                        "棒の長さ＝普段の週と比べた動きの大きさ", "投資の勧誘・助言ではありません"):
            self.assertIn(heading, self.page)
        self.assertIn(self.issue["headline"], self.page)
        self.assertIn(self.issue["quiz"], self.page)
        self.assertIn('href="../index.html"', self.page)

    def test_page_is_never_text_only(self):
        # bars + diagram + focus line + one line per `others` item
        self.assertEqual(self.page.count("<svg"), 1 + 1 + 1 + 2)
        self.assertEqual(render_issue(self.snap, no_theme_issue()).count("<svg"), 1 + 5)

    def test_changes_come_from_snapshot(self):
        self.assertIn("▲3.2%", self.page)
        next(i for i in self.snap["instruments"] if i["id"] == "gold")["change"] = 7.7
        page = render_issue(self.snap, self.issue)
        self.assertIn("▲7.7%", page)
        self.assertNotIn("▲3.2%", page)

    def test_every_edge_explain_and_every_source_url_appears(self):
        for k, edge in enumerate(self.issue["themes"][0]["edges"], 1):
            self.assertIn(edge["explain"], self.page)
            self.assertIn(edge["short"], self.page)
        for src in self.issue["sources"]:
            self.assertIn(f'href="{src["url"]}"', self.page)
            self.assertIn(src["title"], self.page)
        self.assertIn('rel="noopener"', self.page)

    def test_edge_explanations_are_numbered_like_the_diagram(self):
        numbers = re.findall(r'class="num">(\d+)<', self.page)
        self.assertEqual(numbers, ["1", "2", "3", "4", "5"])

    def test_glossary_and_others_content_appear(self):
        self.assertIn("用語メモ", self.page)
        self.assertIn("利下げ観測", self.page)
        wti = self.issue["others"][0]
        self.assertIn(wti["what"], self.page)
        for step in wti["why_steps"]:
            self.assertIn(step, self.page)

    def test_user_text_is_escaped(self):
        self.issue["headline"] = "<img src=x onerror=alert(1)>"
        self.issue["themes"][0]["edges"][0]["explain"] = "a<b & c" * 10
        self.issue["quiz"] = "</script><script>alert(2)</script>"
        self.issue["sources"][0]["title"] = '"><svg onload=alert(3)>'
        page = render_issue(self.snap, self.issue)
        self.assertNotIn("<img src=x", page)
        self.assertNotIn("<script>alert", page)
        self.assertNotIn("<svg onload", page)
        self.assertIn("a&lt;b &amp; c", page)

    def test_source_url_cannot_break_out_of_attribute(self):
        self.issue["sources"][0]["url"] = 'https://jp.reuters.com/x" onclick="alert(1)'
        page = render_issue(self.snap, self.issue)
        self.assertNotIn('" onclick="alert(1)', page)

    def test_unclear_item_shows_no_reason_text(self):
        self.assertIn("はっきりした理由は報じられていません。", self.page)

    def test_no_theme_mode_renders_without_diagram(self):
        page = render_issue(self.snap, no_theme_issue())
        self.assertNotIn("つながりの図", page)
        self.assertNotIn("テーマ以外の大きな動き", page)
        self.assertIn("今週の大きな動き", page)

    def test_no_external_resources(self):
        allowed = {s["url"] for s in self.issue["sources"]}
        for url in re.findall(r'(?:src|href)="(https?:[^"]*)"', self.page):
            self.assertIn(url, allowed)
        self.assertNotIn("@import", self.page)
        self.assertNotIn("<script", self.page)
        self.assertNotIn("<link", self.page)


class IndexAndNoticeTest(unittest.TestCase):
    def test_week_label(self):
        self.assertEqual(week_label(sample_snapshot()), "11/9〜11/13の週")

    def test_issue_url(self):
        self.assertEqual(issue_url(BASE + "/", "2026-11-13"), BASE + "/issues/2026-11-13.html")

    def test_index_lists_newest_first_and_links_relative(self):
        page = render_index([{"week_end": "2026-11-06", "headline": "古い号"},
                             {"week_end": "2026-11-13", "headline": "新しい<号>"}])
        self.assertLess(page.index("issues/2026-11-13.html"), page.index("issues/2026-11-06.html"))
        self.assertIn('href="issues/2026-11-13.html"', page)
        self.assertIn("新しい&lt;号&gt;", page)
        self.assertIn("バックナンバー", page)

    def test_index_with_no_issues(self):
        self.assertIn("まだ", render_index([]))

    def test_notice_is_three_lines_with_url(self):
        text = notice_text(sample_snapshot(), sample_issue(), BASE + "/issues/2026-11-13.html")
        self.assertEqual(text.splitlines(), ["📈 週刊 世界マーケット解説（11/9〜11/13の週）",
                                             "「米国の利下げ観測」が世界を動かした",
                                             BASE + "/issues/2026-11-13.html"])


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, "config"))
        os.makedirs(os.path.join(self.root, "work"))
        self._write("config/site.json", {"base_url": BASE})
        self._write("work/snapshot.json", sample_snapshot())
        self._write("work/issue.json", sample_issue())

    def _write(self, rel, obj):
        with open(os.path.join(self.root, rel), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    def _read(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as f:
            return f.read()

    def _build(self):
        return build(os.path.join(self.root, "work/snapshot.json"),
                     os.path.join(self.root, "work/issue.json"), root=self.root)

    def test_build_writes_page_data_index_and_notice(self):
        url = self._build()
        self.assertEqual(url, BASE + "/issues/2026-11-13.html")
        self.assertIn("今週のテーマ", self._read("docs/issues/2026-11-13.html"))
        self.assertEqual(json.loads(self._read("data/2026-11-13/issue.json")), sample_issue())
        self.assertEqual(json.loads(self._read("data/2026-11-13/snapshot.json")), sample_snapshot())
        self.assertIn(url, self._read("work/notice.txt"))
        self.assertIn("issues/2026-11-13.html", self._read("docs/index.html"))

    def test_cli_rerun_same_week_keeps_single_index_entry(self):
        self._build()
        self._build()
        self.assertEqual(self._read("docs/index.html").count('href="issues/2026-11-13.html"'), 1)

    def test_index_includes_earlier_issues(self):
        os.makedirs(os.path.join(self.root, "data/2026-11-06"))
        self._write("data/2026-11-06/issue.json", {"week_end": "2026-11-06", "headline": "前の週"})
        self._build()
        index = self._read("docs/index.html")
        self.assertIn("前の週", index)
        self.assertLess(index.index("2026-11-13.html"), index.index("2026-11-06.html"))


if __name__ == "__main__":
    unittest.main()
