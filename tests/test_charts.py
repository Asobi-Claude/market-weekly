import re
import unittest
import xml.etree.ElementTree as ET

from scripts.charts import (DOWN, UP, bars_svg, color_for, diagram_svg,
                            fmt_change, line_svg, wrap)
from tests.fixtures import sample_issue, sample_snapshot

SNAP = sample_snapshot()
INSTR = {i["id"]: i for i in SNAP["instruments"]}
FEATURED = [INSTR[k] for k in ("gold", "sp500", "usdjpy", "nikkei", "wti", "dax")]
NS = "{http://www.w3.org/2000/svg}"


def parse(svg):
    return ET.fromstring(svg)


def texts(svg):
    return ["".join(t.itertext()) for t in parse(svg).iter(NS + "text")]


def viewbox(svg):
    return [float(v) for v in parse(svg).get("viewBox").split()]


class FormatTest(unittest.TestCase):
    def test_fmt_change(self):
        self.assertEqual(fmt_change(3.24, "%"), "▲3.2%")
        self.assertEqual(fmt_change(-1.46, "%"), "▼1.5%")
        self.assertEqual(fmt_change(-0.12, "pt"), "▼0.12ポイント")
        self.assertEqual(fmt_change(0.07, "pt"), "▲0.07ポイント")
        self.assertEqual(fmt_change(0.04, "%"), "±0.0%")
        self.assertEqual(fmt_change(-0.004, "pt"), "±0.00ポイント")

    def test_color_for(self):
        self.assertEqual((color_for(1.0), color_for(-1.0)), (UP, DOWN))

    def test_wrap_breaks_into_fixed_width_lines(self):
        self.assertEqual(wrap("あいうえおかきくけこさし", 5), ["あいうえお", "かきくけこ", "さし"])
        self.assertEqual(wrap("", 5), [""])


class BarsTest(unittest.TestCase):
    def test_bars_is_well_formed_and_labelled(self):
        svg = bars_svg(FEATURED)
        self.assertTrue(parse(svg).get("aria-label"))
        joined = " ".join(texts(svg))
        for inst in FEATURED:
            self.assertIn(inst["name"], joined)
            self.assertIn(fmt_change(inst["change"], inst["unit"]), joined)

    def test_bars_use_both_colours_and_stay_inside(self):
        svg = bars_svg(FEATURED)
        self.assertIn(UP, svg)
        self.assertIn(DOWN, svg)
        _, _, width, _ = viewbox(svg)
        for rect in parse(svg).iter(NS + "rect"):
            self.assertGreaterEqual(float(rect.get("x")), 0)
            self.assertLessEqual(float(rect.get("x")) + float(rect.get("width")), width)

    def test_bars_list_risers_first_then_fallers_by_size(self):
        order = [t for t in texts(bars_svg(FEATURED)) if t in {i["name"] for i in FEATURED}]
        self.assertEqual(order, ["金", "米国株 S&P500", "ドイツ株 DAX", "原油 WTI", "日経平均", "ドル/円"])

    def test_bar_length_follows_score(self):
        items = [dict(INSTR["gold"], score=4.0), dict(INSTR["sp500"], score=1.0)]
        widths = sorted(float(r.get("width")) for r in parse(bars_svg(items)).iter(NS + "rect"))
        self.assertAlmostEqual(widths[-1] / widths[0], 4.0, places=1)


class LineTest(unittest.TestCase):
    def test_line_is_well_formed_with_date_labels(self):
        gold = INSTR["gold"]
        svg = line_svg(gold["daily"], [{"date": "2026-11-11", "text": "米雇用統計の発表"}], gold["change"])
        joined = " ".join(texts(svg))
        self.assertIn("11/6", joined)
        self.assertIn("11/13", joined)
        self.assertIn("米雇用統計の発表", joined)
        self.assertIn(UP, svg)

    def test_line_handles_two_points_and_flat_series(self):
        parse(line_svg([["2026-11-06", 5.0], ["2026-11-13", 5.0]], [], 0.0))
        parse(line_svg([["2026-11-13", 5.0]], [], 0.0))

    def test_line_note_on_first_and_last_day_stays_inside_viewbox(self):
        gold = INSTR["gold"]
        long_note = "とても長い注記の文章がここに入りますので折り返しが必要です"
        svg = line_svg(gold["daily"], [{"date": "2026-11-06", "text": long_note},
                                       {"date": "2026-11-13", "text": long_note}], gold["change"])
        _, _, width, _ = viewbox(svg)
        for t in parse(svg).iter(NS + "text"):
            x, anchor = float(t.get("x")), t.get("text-anchor", "start")
            size = float(t.get("font-size", 11))
            longest = max((len(s) for s in t.itertext()), default=0) * size
            left = x if anchor == "start" else x - longest if anchor == "end" else x - longest / 2
            self.assertGreaterEqual(left, -0.5, t.get("x"))
            self.assertLessEqual(left + longest, width + 0.5)

    def test_line_ignores_note_for_unknown_date(self):
        gold = INSTR["gold"]
        svg = line_svg(gold["daily"], [{"date": "2026-01-01", "text": "範囲外"}], gold["change"])
        self.assertNotIn("範囲外", svg)


class DiagramTest(unittest.TestCase):
    def setUp(self):
        self.theme = sample_issue()["themes"][0]

    def test_diagram_has_one_badge_per_edge_and_one_box_per_node(self):
        root = parse(diagram_svg(self.theme, INSTR))
        self.assertEqual(len(list(root.iter(NS + "rect"))), len(self.theme["nodes"]))
        badges = [t for t in texts(diagram_svg(self.theme, INSTR)) if re.fullmatch(r"\d+", t)]
        self.assertEqual(badges, [str(k) for k in range(1, len(self.theme["edges"]) + 1)])

    def test_diagram_shows_snapshot_change_for_instrument_nodes(self):
        joined = " ".join(texts(diagram_svg(self.theme, INSTR)))
        self.assertIn("▲3.2%", joined)
        self.assertIn("▼2.1%", joined)
        self.assertIn("日経平均", joined)

    def test_diagram_boxes_stay_inside_viewbox_and_do_not_overlap(self):
        svg = diagram_svg(self.theme, INSTR)
        _, _, width, height = viewbox(svg)
        boxes = [tuple(float(r.get(k)) for k in ("x", "y", "width", "height")) for r in parse(svg).iter(NS + "rect")]
        for x, y, w, h in boxes:
            self.assertTrue(0 <= x and x + w <= width and 0 <= y and y + h <= height)
        for a in range(len(boxes)):
            for b in range(a + 1, len(boxes)):
                ax, ay, aw, ah = boxes[a]
                bx, by, bw, bh = boxes[b]
                self.assertFalse(ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah)

    def test_text_is_escaped(self):
        self.theme["nodes"][0]["label"] = '<script>alert(1)</script> & "x"'
        svg = diagram_svg(self.theme, INSTR)
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;", svg)
        parse(svg)

    def test_names_and_notes_are_escaped_everywhere(self):
        evil = dict(INSTR["gold"], name='A&B <b>"x"</b>')
        parse(bars_svg([evil, INSTR["wti"]]))
        parse(line_svg(evil["daily"], [{"date": "2026-11-11", "text": "<i>&"}], 1.0))
        parse(diagram_svg(self.theme, dict(INSTR, gold=evil)))


if __name__ == "__main__":
    unittest.main()
