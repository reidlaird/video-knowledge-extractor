from __future__ import annotations

import unittest

from app.ocr_filter import filter_ocr_lines, is_demo_content_ocr, is_noise_ocr_line
from app.text_analysis import best_on_screen_line, build_description, extract_key_terms
from app.transcribe import TranscriptResult, TranscriptSegment
from app.video_analysis import VideoAnalysisResult, VisualFrame


class OcrFilterTests(unittest.TestCase):
    def test_filters_sponsor_and_nav_noise(self) -> None:
        lines = [
            "# Inika admin@linkd.com",
            "Post ajob opening",
            "Integrations",
            "Affordances & Signifiers",
            "Burrito Bowl Today 9.30am",
        ]
        filtered = filter_ocr_lines(lines)
        self.assertIn("Affordances & Signifiers", filtered)
        self.assertNotIn("Integrations", filtered)
        self.assertNotIn("Burrito Bowl Today 9.30am", filtered)
        self.assertTrue(is_noise_ocr_line("# Inika admin@linkd.com"))
        self.assertTrue(is_demo_content_ocr("Burrito Bowl Today 9.30am"))

    def test_filters_demo_nav_labels(self) -> None:
        self.assertTrue(is_demo_content_ocr("Drinks"))
        self.assertTrue(is_demo_content_ocr("The Food Menu"))
        filtered = filter_ocr_lines(["Drinks", "Affordances & Signifiers", "Position"])
        self.assertEqual(filtered, ["Affordances & Signifiers"])

    def test_filters_chat_demo_ui(self) -> None:
        self.assertTrue(is_demo_content_ocr("Hi Nixtio, How can I help you today?"))
        self.assertTrue(is_demo_content_ocr("Product designer based out of Canada driving change through great design"))


class TextAnalysisTests(unittest.TestCase):
    def test_extracts_domain_terms_not_stopwords(self) -> None:
        transcript = TranscriptResult(
            language="en",
            language_probability=0.99,
            duration=560.0,
            text=(
                "Good UI has signifiers and hierarchy. Typography and white space matter. "
                "Dark mode and shadows change contrast."
            ),
            segments=[
                TranscriptSegment(1, 0.0, 5.0, "Good UI has signifiers and hierarchy."),
                TranscriptSegment(2, 5.0, 10.0, "Typography and white space matter."),
                TranscriptSegment(3, 10.0, 15.0, "Dark mode and shadows change contrast."),
            ],
        )
        terms = extract_key_terms(transcript, None)
        self.assertTrue(terms)
        lowered = [term.lower() for term in terms]
        self.assertNotIn("and", lowered)
        self.assertNotIn("the", lowered)
        self.assertTrue(any("hierarchy" in term or "typography" in term or "dark mode" in term for term in lowered))

    def test_prefers_speech_terms_over_menu_ocr(self) -> None:
        transcript = TranscriptResult(
            language="en",
            language_probability=0.99,
            duration=560.0,
            text=(
                "Hierarchy, typography, white space, dark mode, shadows, and micro interactions "
                "are core UI UX concepts. Affordances and signifiers help users understand controls."
            ),
            segments=[
                TranscriptSegment(
                    1,
                    0.0,
                    20.0,
                    "Hierarchy, typography, white space, dark mode, shadows, and micro interactions are core UI UX concepts.",
                ),
                TranscriptSegment(
                    2,
                    20.0,
                    40.0,
                    "Affordances and signifiers help users understand controls.",
                ),
            ],
        )
        visual = VideoAnalysisResult(
            duration=560.0,
            frames_analyzed=3,
            frames=[
                VisualFrame(
                    0.0,
                    "0:00",
                    ocr_text=["Burrito Bowl Today 9.30am", "Affordances & Signifiers"],
                ),
                VisualFrame(
                    30.0,
                    "0:30",
                    ocr_text=["Mushroom Risotto Tagliatelle Penne Alfredo Bolognese"],
                ),
            ],
            ollama_available=False,
            ollama_model=None,
        )
        terms = extract_key_terms(transcript, visual)
        lowered = [term.lower() for term in terms]
        self.assertNotIn("burrito bowl today 9.30am", lowered)
        self.assertNotIn("mushroom risotto tagliatelle penne alfredo bolognese", lowered)
        self.assertTrue(any("hierarchy" in term or "typography" in term or "white space" in term for term in lowered))

    def test_detects_affordances_from_speech_alias(self) -> None:
        transcript = TranscriptResult(
            language="en",
            language_probability=0.99,
            duration=60.0,
            text="Good UI tells the user what a control affords or what it can do.",
            segments=[
                TranscriptSegment(
                    1,
                    0.0,
                    10.0,
                    "Good UI tells the user what a control affords or what it can do.",
                ),
            ],
        )
        terms = extract_key_terms(transcript, None)
        lowered = [term.lower() for term in terms]
        self.assertIn("affordances", lowered)

    def test_dedupes_visual_hierarchy(self) -> None:
        transcript = TranscriptResult(
            language="en",
            language_probability=0.99,
            duration=60.0,
            text="Hierarchy and visual hierarchy guide attention. Typography matters too.",
            segments=[
                TranscriptSegment(1, 0.0, 10.0, "Hierarchy and visual hierarchy guide attention."),
                TranscriptSegment(2, 10.0, 20.0, "Typography matters too."),
            ],
        )
        terms = extract_key_terms(transcript, None)
        lowered = [term.lower() for term in terms]
        self.assertIn("hierarchy", lowered)
        self.assertNotIn("visual hierarchy", lowered)

    def test_best_on_screen_line_skips_unrelated_demo_ui(self) -> None:
        line = best_on_screen_line(
            ["Hi Nixtio, How can I help you today?", "Affordances & Signifiers"],
            "Good UI has signifiers like hover states and button press states.",
        )
        self.assertEqual(line, "Affordances & Signifiers")

    def test_description_uses_key_terms(self) -> None:
        description = build_description(
            title="Every UI/UX Concept Explained in Under 10 Minutes",
            key_terms=["affordances", "hierarchy", "typography", "white space"],
            has_visual=True,
        )
        self.assertIn("affordances", description.lower())
        self.assertIn("Use when the user asks about", description)


if __name__ == "__main__":
    unittest.main()
