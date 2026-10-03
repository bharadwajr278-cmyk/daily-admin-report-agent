from __future__ import annotations

import html
import imaplib
import json
import os
import re
import smtplib
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Any
from zoneinfo import ZoneInfo

import requests


IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class Report:
    report_date: str
    downloads: int | str
    filtered_members: int | str
    usage_day_wise: str
    whatsapp: int | str
    called: int | str
    shared: int | str
    total_query_cost: str
    usage_minutes: str
    data_status: str
    note: str = ""


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def endpoint(base_url: str, path_env: str) -> str:
    path = required_env(path_env)
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def response_json(response: requests.Response, label: str) -> dict[str, Any]:
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} returned an unexpected response")
    return payload


def login() -> requests.Session:
    base_url = required_env("BROKKET_BASE_URL")
    session = requests.Session()
    response = session.post(
        endpoint(base_url, "BROKKET_LOGIN_PATH"),
        json={
            "phone": required_env("BROKKET_PHONE"),
            "countryCode": "+91",
            "otp": "222222",
            "password": required_env("BROKKET_PASSWORD"),
        },
        timeout=30,
    )
    payload = response_json(response, "Brokket login")
    data = payload.get("data") or {}
    token = data.get("accessToken")
    if str(payload.get("code")) != "1000" or not token:
        raise RuntimeError(payload.get("message") or "Brokket login failed")
    session.headers.update({"ACCESS_TOKEN": str(token), "Content-Type": "application/json"})
    return session


def member_summary(
    session: requests.Session, date_iso: str, filter_type: str, registration: str
) -> dict[str, Any]:
    base_url = required_env("BROKKET_BASE_URL")
    response = session.get(
        endpoint(base_url, "BROKKET_MEMBERS_PATH"),
        params={
            "search": "",
            "fromDate": f"{date_iso}T00:00:00",
            "toDate": f"{date_iso}T23:59:59",
            "filterType": filter_type,
            "page": "0",
            "size": "20",
            "registrationFilter": registration,
            "onboardingCityCode": "",
        },
        timeout=60,
    )
    return response_json(response, "Mini CRM")


def query_summary(session: requests.Session, date_iso: str) -> dict[str, Any]:
    base_url = required_env("BROKKET_BASE_URL")
    response = session.post(
        endpoint(base_url, "BROKKET_QUERIES_PATH"),
        params={"page": "0", "size": "20"},
        json={
            "search": "",
            "fromDate": f"{date_iso}T00:00:00",
            "toDate": f"{date_iso}T23:59:59",
            "activityTypes": [],
            "propertyTypes": [],
            "cityCode": None,
        },
        timeout=60,
    )
    payload = response_json(response, "Queries")
    data = payload.get("data") or payload
    return data.get("summary") or {}


def normalise_duration(value: Any) -> str:
    if not value:
        return "0"
    text = str(value)
    replacements = {
        r"\s*\bdays?\b": "D",
        r"\s*\bhours?\b": "H",
        r"\s*\bminutes?\b": "M",
        r"\s*\bseconds?\b": "S",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return " ".join(text.split())


def duration_minutes(value: Any) -> str:
    text = str(value or "0")
    units = {
        "d": 1440,
        "h": 60,
        "m": 1,
        "s": 1 / 60,
    }
    total = 0.0
    found = False
    for amount, unit in re.findall(
        r"(\d+(?:\.\d+)?)\s*(d(?:ays?)?|h(?:ours?)?|m(?:in(?:utes?)?)?|s(?:ec(?:onds?)?)?)",
        text,
        flags=re.IGNORECASE,
    ):
        total += float(amount) * units[unit[0].lower()]
        found = True
    if not found:
        total = float(text)
    return f"{total:.2f}"


def format_query_cost(value: Any) -> str:
    if value is None:
        return "Unavailable"
    number = float(value)
    if number >= 10_000_000:
        return f"₹{number / 10_000_000:.2f} Cr"
    if number >= 100_000:
        return f"₹{number / 100_000:.2f} L"
    return f"₹{number:,.2f}".replace(",", "_").replace("_", ",")


def collect_once(date_iso: str) -> Report:
    notes: list[str] = []
    values: dict[str, Any] = {
        "downloads": "Unavailable",
        "filtered_members": "Unavailable",
        "usage_day_wise": "Unavailable",
        "whatsapp": "Unavailable",
        "called": "Unavailable",
        "shared": "Unavailable",
        "total_query_cost": "Unavailable",
        "usage_minutes": "Unavailable",
    }
    try:
        session = login()
    except Exception as exc:
        notes.append(f"Dashboard authentication failed: {exc}")
        return Report(
            report_date=date_iso,
            data_status="Unavailable",
            note="; ".join(notes),
            **values,
        )

    try:
        joined = member_summary(session, date_iso, "JOINED", "ALL")
        values["downloads"] = joined.get("activeMembers", "Unavailable")
    except Exception as exc:
        notes.append(f"Mini CRM joined-member data unavailable: {exc}")

    try:
        usage = member_summary(session, date_iso, "USAGE", "ALL")
        values["filtered_members"] = usage.get("activeMembers", "Unavailable")
        raw_usage = usage.get("filteredAppUsage")
        if raw_usage is None:
            raise RuntimeError("filteredAppUsage is absent")
        values["usage_day_wise"] = normalise_duration(raw_usage)
        first_calc = duration_minutes(raw_usage)
        second_calc = duration_minutes(raw_usage)
        if first_calc != second_calc:
            raise RuntimeError("independent minute calculations did not match")
        values["usage_minutes"] = first_calc
    except Exception as exc:
        notes.append(f"Usage data unavailable: {exc}")

    try:
        summary = query_summary(session, date_iso)
        counts = summary.get("countByActionType") or {}
        values["whatsapp"] = counts.get("WHATSAPPED", 0)
        values["called"] = counts.get("CALLED", 0)
        values["shared"] = counts.get("SHARED", 0)
        values["total_query_cost"] = format_query_cost(summary.get("totalQueryCost"))
    except Exception as exc:
        notes.append(f"Query data unavailable: {exc}")

    status = "Verified" if not notes and "Unavailable" not in values.values() else "Partially unavailable"
    return Report(report_date=date_iso, data_status=status, note="; ".join(notes), **values)


def report_signature(report: Report) -> str:
    comparable = asdict(report)
    comparable.pop("note", None)
    comparable.pop("data_status", None)
    return json.dumps(comparable, sort_keys=True, ensure_ascii=False)


def collect_verified(date_iso: str) -> Report:
    first = collect_once(date_iso)
    time.sleep(10)
    second = collect_once(date_iso)
    if report_signature(first) == report_signature(second):
        return second
    time.sleep(5)
    third = collect_once(date_iso)
    changed = sorted(
        key
        for key in asdict(third)
        if key not in {"note", "data_status"} and getattr(second, key) != getattr(third, key)
    )
    note_parts = [part for part in [third.note] if part]
    note_parts.append(
        "Validation readings differed; the latest completed reading was used"
        + (f" ({', '.join(changed)})" if changed else "")
        + "."
    )
    return Report(**{**asdict(third), "note": " ".join(note_parts)})


def wait_for_collection_window() -> None:
    now = datetime.now(IST)
    target = now.replace(hour=18, minute=29, second=20, microsecond=0)
    if now < target:
        time.sleep((target - now).total_seconds())


def wait_until_send_time() -> None:
    now = datetime.now(IST)
    target = now.replace(hour=18, minute=30, second=0, microsecond=0)
    if now < target:
        time.sleep((target - now).total_seconds())
    now = datetime.now(IST)
    window_end = now.replace(hour=18, minute=31, second=0, microsecond=0)
    if now >= window_end:
        raise RuntimeError(
            "6:30 PM IST delivery window was missed; email was not sent at another time"
        )


def email_already_sent(subject: str) -> bool:
    sender = required_env("GMAIL_ADDRESS")
    app_password = required_env("GMAIL_APP_PASSWORD")
    with imaplib.IMAP4_SSL("imap.gmail.com", 993) as mailbox:
        mailbox.login(sender, app_password)
        status, _ = mailbox.select('"[Gmail]/Sent Mail"', readonly=True)
        if status != "OK":
            raise RuntimeError("Unable to open Gmail Sent Mail for duplicate check")
        status, message_ids = mailbox.search(None, "SUBJECT", f'"{subject}"')
        if status != "OK":
            raise RuntimeError("Unable to search Gmail Sent Mail for duplicate check")
        return bool(message_ids and message_ids[0].strip())


def display_date(date_iso: str) -> str:
    parsed = datetime.strptime(date_iso, "%Y-%m-%d")
    return parsed.strftime("%d %B %Y")


def report_subject(date_iso: str) -> str:
    base = f"Brokket Daily Admin Report | {date_iso}"
    suffix = os.getenv("REPORT_SUBJECT_SUFFIX", "").strip()
    return f"{base} | {suffix}" if suffix else base


def build_email(report: Report) -> EmailMessage:
    recipient = required_env("REPORT_RECIPIENT")
    sender = required_env("GMAIL_ADDRESS")
    subject = report_subject(report.report_date)
    rows = [
        ("Download App", report.downloads),
        ("Filtered Members", report.filtered_members),
        ("Usage Day Wise", report.usage_day_wise),
        ("WhatsApp", report.whatsapp),
        ("Called", report.called),
        ("Shared", report.shared),
        ("Total Query Cost", report.total_query_cost),
        ("Usage in Minutes", report.usage_minutes),
    ]
    text_rows = "\n".join(f"{label}: {value}" for label, value in rows)
    text_note = f"\n\nData Quality Note: {report.note}" if report.note else ""
    text_body = (
        "BROKKET\nDaily Admin Report\n\n"
        f"Report Date: {display_date(report.report_date)}\n"
        "Time Zone: IST (Asia/Kolkata)\n"
        f"Data Status: {report.data_status}\n\n"
        f"PERFORMANCE SUMMARY\n\n{text_rows}{text_note}\n\n"
        "This is an automated daily report generated from the Brokket Admin Dashboard."
    )
    html_rows = "".join(
        "<tr>"
        f"<td style='padding:11px 14px;border-bottom:1px solid #e5e7eb;color:#475569'>{html.escape(str(label))}</td>"
        f"<td style='padding:11px 14px;border-bottom:1px solid #e5e7eb;text-align:right;color:#0f172a'><strong>{html.escape(str(value))}</strong></td>"
        "</tr>"
        for label, value in rows
    )
    note_html = (
        "<div style='margin-top:18px;padding:12px 14px;background:#fff7ed;border:1px solid #fed7aa;"
        "border-radius:8px;color:#9a3412'><strong>Data Quality Note:</strong> "
        f"{html.escape(report.note)}</div>"
        if report.note
        else ""
    )
    html_body = f"""
    <div style="background:#f8fafc;padding:24px;font-family:Arial,Helvetica,sans-serif;color:#0f172a">
      <div style="max-width:640px;margin:auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden">
        <div style="background:#0f172a;padding:24px 28px;color:#ffffff">
          <div style="font-size:13px;font-weight:700;letter-spacing:2px">BROKKET</div>
          <div style="font-size:25px;font-weight:700;margin-top:6px">Daily Admin Report</div>
        </div>
        <div style="padding:24px 28px">
          <table role="presentation" style="width:100%;font-size:14px;margin-bottom:22px">
            <tr><td style="padding:3px 0;color:#64748b">Report Date</td><td style="padding:3px 0;text-align:right"><strong>{display_date(report.report_date)}</strong></td></tr>
            <tr><td style="padding:3px 0;color:#64748b">Time Zone</td><td style="padding:3px 0;text-align:right"><strong>IST (Asia/Kolkata)</strong></td></tr>
            <tr><td style="padding:3px 0;color:#64748b">Data Status</td><td style="padding:3px 0;text-align:right"><strong>{html.escape(report.data_status)}</strong></td></tr>
          </table>
          <div style="font-size:12px;font-weight:700;letter-spacing:1.2px;color:#64748b;margin-bottom:8px">PERFORMANCE SUMMARY</div>
          <table role="presentation" style="width:100%;border:1px solid #e2e8f0;border-radius:8px;border-collapse:separate;border-spacing:0;overflow:hidden;font-size:14px">
            {html_rows}
          </table>
          {note_html}
          <div style="margin-top:22px;color:#94a3b8;font-size:12px;line-height:1.5">This is an automated daily report generated from the Brokket Admin Dashboard.</div>
        </div>
      </div>
    </div>
    """
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    return message


def send_email(report: Report) -> None:
    sender = required_env("GMAIL_ADDRESS")
    app_password = required_env("GMAIL_APP_PASSWORD")
    message = build_email(report)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as smtp:
        smtp.login(sender, app_password)
        smtp.send_message(message)


def main() -> int:
    today = datetime.now(IST).date().isoformat()
    manual_run = os.getenv("REPORT_RUN_MODE") == "workflow_dispatch"
    report_date = os.getenv("REPORT_DATE", "").strip() if manual_run else today
    if manual_run:
        try:
            datetime.strptime(report_date, "%Y-%m-%d")
        except ValueError as error:
            raise RuntimeError("REPORT_DATE must use YYYY-MM-DD format") from error
    subject = report_subject(report_date)
    if email_already_sent(subject):
        print(f"Report for {report_date} already exists in Sent Mail; skipping duplicate.")
        return 0
    if not manual_run:
        wait_for_collection_window()
    report = collect_verified(report_date)
    if not manual_run:
        wait_until_send_time()
    send_email(report)
    print(json.dumps({"sent": True, "date": report_date, "status": report.data_status}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Brokket report failed: {error}", file=sys.stderr)
        raise
