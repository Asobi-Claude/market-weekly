import unittest

from scripts.issue import featured_ids, host_allowed, layers, validate
from tests.fixtures import ALLOWED, no_theme_issue, sample_issue, sample_snapshot


def errors(mutate=None, issue=None):
    issue = issue or sample_issue()
    if mutate:
        mutate(issue)
    return validate(issue, sample_snapshot(), ALLOWED)


class Base(unittest.TestCase):
    def assertRejected(self, mutate, phrase, issue=None):
        errs = errors(mutate, issue)
        self.assertTrue(any(phrase in e for e in errs), f"{phrase!r} not in {errs}")


class HelpersTest(unittest.TestCase):
    def test_host_allowed(self):
        ok = lambda u: host_allowed(u, ALLOWED)
        self.assertTrue(ok("https://jp.reuters.com/markets/x"))
        self.assertTrue(ok("https://reuters.com/x"))
        self.assertTrue(ok("https://WWW.Reuters.com/x"))
        self.assertTrue(ok("https://www.bls.gov/news.release/empsit.nr0.htm"))
        self.assertTrue(ok("https://www.mof.go.jp/x"))
        self.assertFalse(ok("http://www.reuters.com/x"))
        self.assertFalse(ok("https://reuters.com.evil.example/x"))
        self.assertFalse(ok("https://notreuters.com/x"))
        self.assertFalse(ok("https://example.com/?u=reuters.com"))
        self.assertFalse(ok("https://user@evil.example#.reuters.com"))
        self.assertFalse(ok("https://reuters.com@evil.example/x"))
        self.assertFalse(ok("https://evilgov/x"))
        self.assertFalse(ok("not a url"))
        self.assertFalse(ok(""))
        self.assertFalse(ok(None))

    def test_featured_ids_in_order_of_appearance(self):
        self.assertEqual(featured_ids(sample_issue()), ["gold", "sp500", "usdjpy", "nikkei", "wti", "dax"])

    def test_layers_by_longest_path(self):
        self.assertEqual(layers(sample_issue()["themes"][0]),
                         [["jobs"], ["rates"], ["n_gold", "n_sp500", "n_usdjpy"], ["n_nikkei"]])

    def test_layers_raises_on_cycle(self):
        theme = sample_issue()["themes"][0]
        theme["edges"].append({"from": "n_nikkei", "to": "rates"})
        with self.assertRaises(ValueError):
            layers(theme)


class ValidTest(Base):
    def test_sample_is_valid(self):
        self.assertEqual(errors(), [])

    def test_all_others_mode_without_themes_is_valid(self):
        self.assertEqual(errors(issue=no_theme_issue()), [])

    def test_validate_reports_all_errors_not_just_first(self):
        def mutate(i):
            i["quiz"] = ""
            i["sources"][0]["url"] = "https://example.com/x"
        self.assertGreaterEqual(len(errors(mutate)), 2)

    def test_validate_does_not_crash_on_garbage(self):
        snap = sample_snapshot()
        for bad in ({}, [], None, "x", {"themes": "x", "others": 3, "sources": {}},
                    {"themes": [None, {"nodes": [1, {}], "edges": [None, {"from": []}], "focus": [3]}],
                     "others": [None, {"sources": 5}], "sources": [None, {"id": []}]}):
            self.assertTrue(validate(bad, snap, ALLOWED), bad)


class RulesTest(Base):
    def test_rule1_week_end_must_match_snapshot(self):
        self.assertRejected(lambda i: i.update(week_end="2026-11-06"), "week_end")

    def test_rule2_headline_and_quiz(self):
        self.assertRejected(lambda i: i.update(headline=""), "headline")
        self.assertRejected(lambda i: i.update(headline="あ" * 41), "headline")
        self.assertRejected(lambda i: i.update(quiz="  "), "quiz")

    def test_rule3_at_most_two_themes(self):
        self.assertRejected(lambda i: i.update(themes=i["themes"] * 3), "themes")

    def test_rule4_five_to_seven_instruments(self):
        self.assertRejected(lambda i: i["others"].clear(), "5〜7")

    def test_rule4_instrument_must_not_appear_twice(self):
        def mutate(i):
            i["others"][1]["instrument"] = "gold"
        self.assertRejected(mutate, "2回")

    def test_rule4_must_be_in_top_ten(self):
        def mutate(i):
            i["others"][1]["instrument"] = "btc"   # rank 11
        self.assertRejected(mutate, "10位")

    def test_rule4_must_include_top_three(self):
        def mutate(i):
            i["others"][0]["instrument"] = "us10y"  # drops wti (rank 2)
        self.assertRejected(mutate, "wti")

    def test_rule5_node_checks(self):
        t = lambda i: i["themes"][0]
        self.assertRejected(lambda i: t(i)["nodes"].append(dict(t(i)["nodes"][1])), "重複")
        self.assertRejected(lambda i: t(i)["nodes"][1].update(type="cause"), "type")
        self.assertRejected(lambda i: t(i)["nodes"][2].update(instrument="nope"), "nope")
        self.assertRejected(lambda i: t(i)["nodes"][0].update(type="mechanism"), "event")
        self.assertRejected(lambda i: t(i)["nodes"][1].update(label=""), "label")

    def test_rule5_node_count(self):
        def mutate(i):
            i["themes"][0]["nodes"] = i["themes"][0]["nodes"][:2]
        self.assertRejected(mutate, "3〜9")

    def test_rule6_edges_reference_existing_nodes(self):
        self.assertRejected(lambda i: i["themes"][0]["edges"][0].update(to="ghost"), "ghost")

    def test_rule6_no_cycles(self):
        def mutate(i):
            i["themes"][0]["edges"].append({"from": "n_nikkei", "to": "rates", "short": "x",
                                            "explain": "あ" * 40, "sources": []})
        self.assertRejected(mutate, "循環")

    def test_rule6_non_event_nodes_need_incoming_edge(self):
        def mutate(i):
            i["themes"][0]["edges"] = [e for e in i["themes"][0]["edges"] if e["to"] != "n_gold"]
        self.assertRejected(mutate, "n_gold")

    def test_rule6_at_most_three_nodes_per_layer(self):
        def mutate(i):
            i["themes"][0]["edges"][4]["from"] = "rates"   # nikkei joins the 3-wide layer
        self.assertRejected(mutate, "段")

    def test_rule7_edge_text_lengths(self):
        e = lambda i: i["themes"][0]["edges"][0]
        self.assertRejected(lambda i: e(i).update(short=""), "short")
        self.assertRejected(lambda i: e(i).update(short="あ" * 25), "short")
        self.assertRejected(lambda i: e(i).update(explain="短い"), "explain")

    def test_rule8_event_needs_source(self):
        self.assertRejected(lambda i: i["themes"][0]["nodes"][0].update(sources=[]), "出典")

    def test_rule9_focus(self):
        t = lambda i: i["themes"][0]
        self.assertRejected(lambda i: t(i).update(focus=[]), "focus")
        self.assertRejected(lambda i: t(i)["focus"][0].update(instrument="wti"), "focus")
        self.assertRejected(lambda i: t(i)["focus"][0]["notes"][0].update(date="2026-11-08"), "2026-11-08")
        self.assertRejected(lambda i: t(i)["focus"][0]["notes"][0].update(text=""), "notes")

    def test_rule10_others(self):
        o = lambda i: i["others"][0]
        self.assertRejected(lambda i: o(i).update(what=""), "what")
        self.assertRejected(lambda i: o(i).update(why_steps=["1つだけ"]), "why_steps")
        self.assertRejected(lambda i: o(i).update(sources=[]), "出典")
        self.assertRejected(lambda i: o(i).update(instrument="nope"), "nope")

    def test_rule10_unclear_item_needs_no_reason(self):
        self.assertEqual(errors(lambda i: i["others"][1].update(why_steps=[], sources=[])), [])

    def test_rule11_no_theme_needs_five_others(self):
        def mutate(i):
            i["others"].pop()
        self.assertRejected(mutate, "5", issue=no_theme_issue())

    def test_rule12_sources(self):
        s = lambda i: i["sources"][0]
        self.assertRejected(lambda i: s(i).update(url="https://example.com/x"), "example.com")
        self.assertRejected(lambda i: s(i).update(url="http://jp.reuters.com/x"), "http://")
        self.assertRejected(lambda i: s(i).update(publisher=""), "publisher")
        self.assertRejected(lambda i: s(i).update(title=""), "title")
        self.assertRejected(lambda i: i["sources"][1].update(id="s1"), "重複")

    def test_rule13_referenced_sources_exist_and_all_are_used(self):
        self.assertRejected(lambda i: i["others"][0].update(sources=["s9"]), "s9")
        self.assertRejected(lambda i: i["sources"].append(
            {"id": "s4", "publisher": "AP", "title": "t", "url": "https://apnews.com/x"}), "s4")

    def test_rule14_glossary(self):
        self.assertRejected(lambda i: i["themes"][0]["glossary"][0].update(text=""), "glossary")


if __name__ == "__main__":
    unittest.main()
