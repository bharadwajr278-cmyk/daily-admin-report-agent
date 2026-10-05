import unittest
from datetime import datetime
from unittest.mock import patch

from main import (
    Report,
    build_email,
    collect_once,
    duration_minutes,
    format_query_cost,
    normalise_duration,
    report_subject,
    report_signature,
    seconds_until_send_window,
)


class ReportTests(unittest.TestCase):
    def test_duration_conversion(self):
        self.assertEqual(duration_minutes("12H 23M 13S"), "743.22")
        self.assertEqual(duration_minutes("1D 12H 32M 57S"), "2192.95")

    def test_duration_normalisation(self):
        self.assertEqual(normalise_duration("1 day 2 hours 3 minutes 4 seconds"), "1D 2H 3M 4S")

    def test_send_window_before_target(self):
        self.assertEqual(
            seconds_until_send_window(datetime(2026, 10, 5, 11, 54, 20)),
            40.0,
        )

    def test_send_window_at_target(self):
        self.assertEqual(
            seconds_until_send_window(datetime(2026, 10, 5, 11, 55, 0)),
            0.0,
        )

    def test_send_window_after_deadline(self):
        self.assertIsNone(
            seconds_until_send_window(datetime(2026, 10, 5, 11, 56, 0))
        )

    def test_query_cost(self):
        self.assertEqual(format_query_cost(46_765_000_000), "₹4676.50 Cr")
        self.assertEqual(format_query_cost(5_445_700_000), "₹544.57 Cr")

    @patch.dict("os.environ", {"REPORT_SUBJECT_SUFFIX": "Corrected"})
    def test_corrected_subject_suffix(self):
        self.assertEqual(
            report_subject("2026-10-02"),
            "Brokket Daily Admin Report | 2026-10-02 | Corrected",
        )

    @patch.dict(
        "os.environ",
        {
            "GMAIL_ADDRESS": "sender@example.com",
            "REPORT_RECIPIENT": "primary@example.com",
            "REPORT_CC": "additional@example.com",
            "SEND_ADDITIONAL_ONLY": "false",
            "REPORT_SUBJECT_SUFFIX": "",
        },
    )
    def test_only_primary_recipient_is_used(self):
        report = Report(
            report_date="2026-10-03",
            downloads=73,
            filtered_members=213,
            usage_day_wise="1D 12H 32M 57S",
            whatsapp=4,
            called=28,
            shared=1,
            total_query_cost="₹467.65 Cr",
            usage_minutes="2192.95",
            data_status="Verified",
            note="",
        )
        message = build_email(report)
        self.assertEqual(message["To"], "primary@example.com")
        self.assertIsNone(message["Cc"])

    @patch("main.query_summary")
    @patch("main.member_summary")
    @patch("main.login")
    def test_joined_and_usage_member_mapping(self, mock_login, mock_member_summary, mock_query_summary):
        mock_login.return_value = object()

        def summary(_session, _date, filter_type, _member_type):
            if filter_type == "JOINED":
                return {"activeMembers": 73}
            return {"activeMembers": 213, "filteredAppUsage": "1D 12H 32M 57S"}

        mock_member_summary.side_effect = summary
        mock_query_summary.return_value = {
            "countByActionType": {"WHATSAPPED": 4, "CALLED": 28, "SHARED": 1},
            "totalQueryCost": 46_765_000_000,
        }

        report = collect_once("2026-10-02")
        self.assertEqual(report.downloads, 73)
        self.assertEqual(report.filtered_members, 213)
        self.assertEqual(report.usage_day_wise, "1D 12H 32M 57S")
        self.assertEqual(report.usage_minutes, "2192.95")

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
