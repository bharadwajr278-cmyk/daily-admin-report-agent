import unittest

from main import Report, duration_minutes, format_query_cost, normalise_duration, report_signature


class ReportTests(unittest.TestCase):
    def test_duration_conversion(self):
        self.assertEqual(duration_minutes("12H 23M 13S"), "743.22")
        self.assertEqual(duration_minutes("1D 12H 32M 57S"), "2192.95")

    def test_duration_normalisation(self):
        self.assertEqual(normalise_duration("1 day 2 hours 3 minutes 4 seconds"), "1D 2H 3M 4S")

    def test_query_cost(self):
        self.assertEqual(format_query_cost(46_765_000_000), "₹4676.50 Cr")
        self.assertEqual(format_query_cost(5_445_700_000), "₹544.57 Cr")

    def test_signature_ignores_notes(self):
        base = dict(
            report_date="2026-10-02",
            downloads=44,
            filtered_members=73,
            usage_day_wise="1D 12H 32M 57S",
            whatsapp=7,
            called=29,
            shared=3,
            total_query_cost="₹544.57 Cr",
            usage_minutes="2192.95",
            data_status="Verified",
        )
        self.assertEqual(
            report_signature(Report(**base, note="first")),
            report_signature(Report(**base, note="second")),
        )


if __name__ == "__main__":
    unittest.main()
