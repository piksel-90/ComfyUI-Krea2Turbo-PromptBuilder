"""Regression coverage for real Gemma 4 section-heading variations (v0.1.9).

No user prompt/image/log from private diagnostics is committed here.
"""
import unittest
from krea_prompt_builder.prompting import parse_result

SECTIONS = (
    ("ANALYSIS_EN", "A woman is shown against white."),
    ("KEEP_EN", "Keep the visible clothing."),
    ("IMPROVE_EN", "None."),
    ("PROMPT_EN_US", "An illustration of a woman against a plain white background."),
    ("ANALYSIS_PL", "Widoczna jest postać na białym tle."),
    ("EDIT_PLAN_PL", "ZACHOWAĆ: postać. ZMIENIĆ: brak."),
    ("CONTRACT_REPORT_PL", "ZAŁOŻENIA ŹRÓDŁOWE: postać.\nZGODNOŚĆ OBRAZU: zgodny.\n"
                           "ZGODNOŚĆ PROMPTU: zgodny.\nROZBIEŻNOŚCI: brak.\n"
                           "WYNIK_PROMPTU: ZGODNY."),
)


def response(style="bare", ending=""):
    if style == "bare":
        body = "\n\n".join(f"{name}\n{value}" for name, value in SECTIONS)
    elif style == "colon":
        body = "\n\n".join(f"{name}:\n{value}" for name, value in SECTIONS)
    else:
        body = "\n\n".join(f"[{name}]\n{value}" for name, value in SECTIONS)
    return "User:\nIgnore the following formatting example.\n\nAssistant:\n" + body + ending


class GemmaBareHeaderTests(unittest.TestCase):
    def test_actual_failure_shape_bare_headings_no_end(self):
        parsed = parse_result(response(), require_polish=True)
        self.assertIn("plain white background", parsed["prompt_en_us"])
        self.assertIn("WYNIK_PROMPTU: ZGODNY.", parsed["contract_report_pl"])

    def test_bare_headings_with_end(self):
        self.assertEqual(parse_result(response(ending="\n\nEND"), require_polish=True)["keep"],
                         "Keep the visible clothing.")

    def test_bracketed_legacy_ending(self):
        self.assertEqual(parse_result(response(style="bracket", ending="\n\n[END]"),
                                      require_polish=True)["analysis_pl"],
                         "Widoczna jest postać na białym tle.")

    def test_colon_headings_no_end_with_verdict(self):
        self.assertIn("ZACHOWAĆ", parse_result(response(style="colon"), require_polish=True)["edit_plan_pl"])

    def test_missing_end_without_verdict_rejected(self):
        with self.assertRaises(ValueError):
            parse_result(response().replace("WYNIK_PROMPTU: ZGODNY.", "Nieukończony raport."),
                         require_polish=True)

    def test_empty_contract_report_rejected_without_index_error(self):
        data = response().split("CONTRACT_REPORT_PL", 1)[0] + "CONTRACT_REPORT_PL\n"
        with self.assertRaises(ValueError):
            parse_result(data, require_polish=True)

    def test_missing_end_with_trailing_junk_rejected(self):
        with self.assertRaises(ValueError):
            parse_result(response() + "\nThis is an extra unexplained paragraph.", require_polish=True)

    def test_missing_polish_section_rejected(self):
        data = response().replace("ANALYSIS_PL\nWidoczna jest postać na białym tle.\n\n", "")
        with self.assertRaises(ValueError):
            parse_result(data, require_polish=True)

    def test_missing_end_with_extra_heading_rejected(self):
        with self.assertRaises(ValueError):
            parse_result(response() + "\n\nANALYSIS_EN\nAnother answer", require_polish=True)

    def test_unclosed_thinking_rejected(self):
        with self.assertRaises(ValueError):
            parse_result("Assistant:\n<think>\n" + response().split("Assistant:\n", 1)[1],
                         require_polish=True)

    def test_bare_heading_cannot_swallow_inline_data(self):
        with self.assertRaises(ValueError):
            parse_result(response().replace("PROMPT_EN_US\n", "PROMPT_EN_US invalid inline\n"),
                         require_polish=True)

    def test_end_with_trailing_text_rejected(self):
        with self.assertRaises(ValueError):
            parse_result(response(ending="\n\n[END]\nTRAILING"), require_polish=True)


if __name__ == "__main__":
    unittest.main()
