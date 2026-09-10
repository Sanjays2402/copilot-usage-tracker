# Security

Copilot Usage Tracker is built for enterprise security reviews. This document
states the threat model, what the app does with credentials and data, and how
to verify a release.

## Summary for reviewers

| Question | Answer |
|---|---|
| What network calls does it make? | **Read-only** `GET` requests to your GitHub API endpoint only (`api.github.com` or your GHES host). No third-party telemetry, no analytics, no phone-home. |
| What permissions does the token need? | Read access to Copilot business/enterprise metrics (`read:org` on classic PATs, or the Copilot metrics read permission on fine-grained tokens). Write scopes are never used. |
| Where is the token stored? | **Never by the app.** It is resolved per process from `GITHUB_TOKEN` → OS keyring → `gh` CLI session → hidden prompt. It is masked in the UI, excluded from `repr`, and never written to the audit log, config files, or the database. |
| Where does usage data live? | A local SQLite database on the user's machine. Nothing is uploaded anywhere. |
| Can it change anything in GitHub? | No. The codebase contains no `POST`/`PUT`/`PATCH`/`DELETE` calls to GitHub's API (the only `POST` in the product is the optional user-configured Slack/Teams webhook for budget alerts). |
| Is it open source? | Yes — MIT licensed. Every release is built in public GitHub Actions with [build provenance attestation](https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds). |

## Threat model

**In scope:** a compromised or curious insider reading the local database;
token leakage via logs, files, or the UI; the app being tricked into
calling an unexpected host (SSRF via `api_base`); supply-chain tampering of
the distributed installers.

**Out of scope:** compromise of the user's own machine or OS keyring;
GitHub's own API security; physical device theft (use disk encryption).

## How each threat is handled

- **Token leakage** — the token lives only in process memory. `auth.py`
  resolves it once per process; it never touches disk, the audit log, or
  crash reports. The dashboard masks it (`ghp_…abcd`) and the setup page
  shows the token's advertised OAuth scopes with a least-privilege verdict.
- **Over-privileged tokens** — the dashboard's Security tab inspects the
  token's scopes and warns when write/admin scopes are present. The app
  itself only needs read access.
- **Unexpected network calls** — every GitHub API call is appended to a
  local JSONL audit log (method, host, path, allowlisted query params,
  status; auth headers never recorded). The Security tab summarizes this
  log live: request counts by method and any non-GitHub hosts. Compliance
  teams can ship the log to their SIEM.
- **Data minimization** — enterprise policy (`policy.yaml`) supports
  aggregate-only mode (no per-user rows), salted user pseudonymization,
  scope allowlists, and retention with automatic purge.
- **Local data control** — the Security tab shows a full inventory of local
  tables with row counts and a "Delete all local data" button.
- **Supply chain** — releases are built on GitHub-hosted runners from
  tagged commits; each installer ships with a SLSA build-provenance
  attestation and an SBOM, so you can verify *this exact binary* came from
  *this exact source commit*.

## Verifying a release

1. Download the installer and its `.sbom.txt` from the
   [Releases page](https://github.com/Sanjays2402/copilot-usage-tracker/releases).
2. Verify build provenance:
   ```bash
   gh attestation verify CopilotUsageTracker-Setup-0.2.1.exe \
     --repo Sanjays2402/copilot-usage-tracker
   ```
3. Compare the SBOM against the dependencies you approve.

## Code signing status

- **Windows:** the installer is currently **unsigned**, so SmartScreen shows
  an "Unknown publisher" prompt. This is the single biggest trust gap and is
  fixed by purchasing a code-signing certificate (the build already supports
  signing via the `CODESIGN_THUMBPRINT` secret when available).
- **macOS:** the DMG is ad-hoc signed; full Developer ID signing +
  notarization runs automatically when the `APPLE_*` secrets are configured.

## Reporting a vulnerability

Please open a GitHub issue or contact the maintainer directly. Do not
include tokens or customer data in reports.
