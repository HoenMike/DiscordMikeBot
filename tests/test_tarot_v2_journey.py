import unittest

from features.tarot.reading.journey import summarize_journey
from features.tarot.renderer import render_journey_card_to_bytes


def reading(created_at, spread, topic, cards, mood=""):
    return {
        "created_at": created_at,
        "spread_type": spread,
        "topic_tag": topic,
        "mood_tag": mood,
        "cards": cards,
    }


def card(card_id, name, reversed=False):
    return {
        "id": card_id,
        "name_vi": name,
        "is_reversed": reversed,
    }


class TarotJourneyAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.history = [
            reading(
                "2026-10-04 10:00:00",
                "custom",
                "decision",
                [
                    card("major_09", "Ẩn Sĩ", True),
                    card("cups_02", "2 Ly"),
                    card("swords_02", "2 Kiếm"),
                ],
                "Cân nhắc",
            ),
            reading(
                "2026-10-03 10:00:00",
                "ppf",
                "clarity",
                [
                    card("major_09", "Ẩn Sĩ", True),
                    card("cups_03", "3 Ly"),
                    card("wands_01", "1 Gậy"),
                ],
                "Rõ ràng",
            ),
            reading(
                "2026-10-01 10:00:00",
                "ppf",
                "decision",
                [
                    card("major_01", "Pháp Sư"),
                    card("pentacles_02", "2 Tiền"),
                    card("cups_02", "2 Ly"),
                ],
                "Cân nhắc",
            ),
        ]

    def test_summary_uses_stored_card_statistics_only(self):
        summary = summarize_journey(self.history, days=30)
        self.assertEqual(summary.reading_count, 3)
        self.assertEqual(summary.total_cards, 9)
        self.assertEqual(summary.major_count, 3)
        self.assertEqual(summary.major_ratio, 33)
        self.assertEqual(summary.suit_counts["cups"], 3)
        self.assertEqual(sum(summary.suit_percentages.values()), 100)

    def test_repeats_and_reversed_repeats_are_counted(self):
        summary = summarize_journey(self.history)
        repeats = {item.name: item.count for item in summary.repeated_cards}
        reversed_repeats = {
            item.name: item.count for item in summary.repeated_reversed_cards
        }
        self.assertEqual(repeats["Ẩn Sĩ"], 2)
        self.assertEqual(repeats["2 Ly"], 2)
        self.assertEqual(reversed_repeats["Ẩn Sĩ"], 2)

    def test_theme_progression_is_chronological_and_compressed(self):
        summary = summarize_journey(self.history)
        self.assertEqual(
            summary.theme_progression,
            ("decision", "clarity", "decision"),
        )
        self.assertEqual(summary.most_used_spread, "ppf")

    def test_empty_history_is_safe(self):
        summary = summarize_journey([], days=30)
        self.assertFalse(summary.has_data)
        self.assertEqual(summary.major_ratio, 0)
        self.assertEqual(summary.theme_progression, ())

    def test_journey_renderer_returns_png(self):
        summary = summarize_journey(self.history)
        buffer = render_journey_card_to_bytes(summary, "Mai")
        self.assertEqual(buffer.read(8), b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
