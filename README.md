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

The report is scheduled **daily for 7:00 PM IST only**. GitHub starts the workflow at 6:30 PM IST so the program can wait for the final collection window, verify two complete current-day readings, recalculate usage minutes independently, and send during the 7:00 PM minute. Manual workflow runs execute the unit tests but never send an email. If GitHub starts too late and the 7:00:00–7:00:59 PM IST delivery window is missed, the job fails without sending at another time.

## Local tests

```powershell
python -m unittest -v test_main.py
```
