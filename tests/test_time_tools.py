"""Tests for the time and date tools. Fixed dates keep results deterministic.

Run: python3 -m unittest discover -s tests -v
"""

import unittest

from agent import ToolRegistry
from agent.time_tools import register_time_tools


def make_registry():
    registry = ToolRegistry()
    register_time_tools(registry)
    return registry


class TimeToolTests(unittest.TestCase):
    def setUp(self):
        self.r = make_registry()

    def call(self, name, **args):
        return self.r.call(name, args)

    # Questions the models got wrong in Runs 3-4 (reference date 2026-10-29)
    def test_day_after_tomorrow(self):
        out = self.call("resolve_date", expression="day after tomorrow", reference="2026-10-29")
        self.assertIn("2026-10-31 (Saturday)", out)

    def test_weeks_left_in_year(self):
        out = self.call("date_difference", start="2026-10-29", end="2026-12-31")
        self.assertIn("63 days (D-63)", out)
        self.assertIn("9 weeks and 0 days", out)

    def test_days_left_in_month(self):
        self.assertIn("2 days left in the month after 2026-10-29", self.call("date_info", date="2026-10-29"))

    def test_hundred_days_later(self):
        out = self.call("add_to_date", date="2026-10-29", days=100)
        self.assertIn("= 2027-02-06 (Saturday)", out)

    def test_week_number_and_quarter(self):
        out = self.call("date_info", date="2026-10-29")
        self.assertIn("2026-W44", out)
        self.assertIn("Q4", out)
        self.assertIn("Leap year: no", out)

    # add_to_date
    def test_month_end_is_clamped(self):
        self.assertIn("= 2027-02-28", self.call("add_to_date", date="2027-01-31", months=1))

    def test_negative_and_clock_arithmetic(self):
        self.assertIn("= 2026-07-31", self.call("add_to_date", date="2026-10-31", months=-3))
        self.assertIn("= 2026-11-01 00:15", self.call("add_to_date", date="2026-10-31 21:30", hours=2, minutes=45))

    def test_korean_anniversary(self):
        out = self.call("add_to_date", date="2026-10-31", days=100, start_is_day_one=True)
        self.assertIn("= 2027-02-07", out)

    def test_string_numbers_are_coerced(self):
        self.assertIn("= 2026-11-10", self.call("add_to_date", date="2026-10-31", days="10"))

    # date_difference
    def test_age(self):
        out = self.call("date_difference", start="2002-04-08", end="2026-10-31")
        self.assertIn("24 years, 6 months and 23 days", out)

    def test_past_date_and_korean_count(self):
        past = self.call("date_difference", start="2026-10-31", end="2026-10-01")
        self.assertIn("D+30", past)
        future = self.call("date_difference", start="2026-10-31", end="2026-11-02")
        self.assertIn("day 3", future)

    def test_phrase_as_date(self):
        out = self.call("date_difference", start="2026-10-31", end="2026-12-25")
        self.assertIn("55 days", out)

    # resolve_date (2026-10-31 is a Saturday)
    def test_weekday_phrases(self):
        ref = "2026-10-31"
        self.assertIn("2026-11-06 (Friday)", self.call("resolve_date", expression="next friday", reference=ref))
        self.assertIn("2026-10-30 (Friday)", self.call("resolve_date", expression="this friday", reference=ref))
        self.assertIn("2026-11-02 (Monday)", self.call("resolve_date", expression="coming monday", reference=ref))
        self.assertIn("2026-10-23 (Friday)", self.call("resolve_date", expression="last friday", reference=ref))

    def test_ranges_and_offsets(self):
        ref = "2026-10-31"
        self.assertIn("2026-11-07 (Saturday) to 2026-11-08 (Sunday)",
                      self.call("resolve_date", expression="next weekend", reference=ref))
        self.assertIn("2026-11-30", self.call("resolve_date", expression="end of next month", reference=ref))
        self.assertIn("2026-11-21", self.call("resolve_date", expression="in 3 weeks", reference=ref))
        self.assertIn("2026-10-21", self.call("resolve_date", expression="10 days ago", reference=ref))

    def test_unknown_phrase_lists_supported_forms(self):
        self.assertIn("Supported:", self.call("resolve_date", expression="sometime soon"))

    # time zones
    def test_current_time_in_city(self):
        out = self.call("get_current_time", timezone="New York")
        self.assertIn("America/New_York", out)

    def test_local_words_mean_local_time(self):
        # Run 5: qwen3:8b sent timezone="user" for "What day of the week is it today?"
        local = self.call("get_current_time")
        for word in ("user", "local", "here", "My"):
            out = self.call("get_current_time", timezone=word)
            self.assertNotIn("Error", out)
            self.assertEqual(out.split(", ", 1)[1], local.split(", ", 1)[1])

    def test_unknown_timezone_suggests(self):
        out = self.call("get_current_time", timezone="Asia/Seol")
        self.assertIn("Did you mean", out)
        self.assertIn("Asia/Seoul", out)

    def test_convert_timezone_with_dst(self):
        # London is on GMT (UTC+0) after 2026-10-25 and on BST (UTC+1) before.
        winter = self.call("convert_timezone", time="2026-11-02 15:00", from_timezone="London", to_timezone="Seoul")
        self.assertIn("= 2026-11-03 00:00", winter)
        summer = self.call("convert_timezone", time="2026-07-01 15:00", from_timezone="London", to_timezone="Seoul")
        self.assertIn("= 2026-07-01 23:00", summer)

    def test_convert_needs_a_zone(self):
        self.assertIn("Error", self.call("convert_timezone", time="15:00"))


if __name__ == "__main__":
    unittest.main()
