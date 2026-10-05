# Private Daily Admin Report Agent

This private repository runs a daily reporting workflow on GitHub-hosted infrastructure, so the laptop does not need to remain powered on.

## Security design

- No dashboard URL, API route, account identifier, password, or email credential is stored in repository files.
- All sensitive configuration is loaded only from encrypted GitHub Actions Secrets.
- Workflow permissions are read-only.
- Secrets are never printed by the application.
- The email is checked in Sent Mail before delivery to prevent duplicates.

## Required GitHub Actions Secrets

Add these under **Settings → Secrets and variables → Actions**:

- `BROKKET_BASE_URL`
- `BROKKET_LOGIN_PATH`
- `BROKKET_MEMBERS_PATH`
- `BROKKET_QUERIES_PATH`
- `BROKKET_PHONE`
- `BROKKET_PASSWORD`
- `GMAIL_ADDRESS`
- `GMAIL_APP_PASSWORD`
- `REPORT_RECIPIENT`

Never add secret values to source files, workflow YAML, commits, issues, pull requests, or workflow logs.

## Schedule

The report is scheduled **daily for 6:00 PM IST** and is sent to `REPORT_RECIPIENT`, with the optional `REPORT_CC` secret receiving a copy. Because GitHub cron is best-effort, automatic backup triggers run between 4:00 PM and 5:45 PM IST. Workflow concurrency keeps only the newest run alive. It collects and double-checks current-day data from 5:58 PM, then waits until 6:00:00 PM before opening the SMTP connection. If GitHub delays every backup past 6:00 PM, the verified current-day report is sent as soon as the delayed run starts instead of silently skipping the day. A duplicate check against Gmail Sent Mail prevents recovery runs from sending the same dated report twice.

The manual workflow button is retained only for recovery/testing. When used, it generates the current-day report and does not change the automatic daily schedule.

## Local tests

```powershell
python -m unittest -v test_main.py
```
