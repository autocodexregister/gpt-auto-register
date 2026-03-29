# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the web management UI (FastAPI, port 18421)
python server.py

# Run batch registration directly (interactive prompts for proxy, count, workers)
python ncs_register.py

# Run the local auto-scheduler (checks every hour, triggers registration when below threshold)
python auto_scheduler.py

# Run the GitHub Actions entry point locally (reads env vars instead of config.json)
python scripts/check_and_register.py
```

## Configuration

Local config lives in `config.json` (gitignored). Copy from `config.example.json` and fill in values. In GitHub Actions (`MODE=github`), all config comes from environment variables mapped from GitHub Secrets/Variables — proxy settings are ignored in this mode.

Key config fields:
- `mail_provider`: `"duckmail"` or `"cfmail"`
- `cpa_base_url` + `cpa_management_key`: CPA (CLIProxyAPI) platform credentials
- `sub2api_base_url` + `sub2api_bearer`: Sub2Api platform credentials
- `upload_api_url` / `upload_api_token`: auto-derived from `cpa_base_url` / `cpa_management_key` if not set explicitly

## Architecture

### Core Components

**`ncs_register.py`** — The registration engine. Handles the full ChatGPT account registration flow using `curl_cffi` (browser impersonation). Supports two mail providers (DuckMail API, CF self-hosted mail), proxy pools with validation, OAuth PKCE flow, and auto-upload to CPA and Sub2Api platforms after successful registration. The public API is `run_batch(total_accounts, output_file, max_workers, proxy, cpa_cleanup)`.

**`server.py`** — FastAPI web management server on port 18421. Provides a browser UI (`web/`) for triggering registrations, monitoring live logs via SSE, and managing accounts on both CPA and Sub2Api platforms. Registration tasks run in a separate subprocess (multiprocessing) with stdout redirected to a queue → SSE stream. Imports `ncs_register` as a module.

**`auto_scheduler.py`** — Local long-running scheduler. Probes CPA `auth-files` endpoint every hour (concurrent probing with 401/403 auto-deletion), triggers `ncs_register.py` as a subprocess when valid account count falls below threshold.

**`scripts/check_and_register.py`** — GitHub Actions entry point. Reads all config from environment variables, checks Sub2Api total account count, and calls `ncs_register.run_batch()` directly when below threshold. Writes outputs to `GITHUB_OUTPUT` and `GITHUB_STEP_SUMMARY`.

### Two Deployment Modes

- **Local** (`mode: default`): Uses `config.json`, proxy pools enabled, web UI or scheduler for orchestration.
- **GitHub Actions** (`MODE=github`): All config from env vars, proxies disabled, `scripts/check_and_register.py` is the entry point, runs on cron (`20 * * * *`) or manual dispatch.

### Data Flow

Registration produces three output formats:
1. `registered_accounts.txt` — plain text list
2. `ak.txt` / `rk.txt` — access key / refresh key files
3. `codex_tokens/*.json` — per-account JSON token files (one file per email)

These get auto-uploaded to CPA (`/v0/management/auth-files`) and/or Sub2Api (`/api/v1/admin/accounts`) if configured.

### CPA URL Normalization

`cpa_base_url` accepts multiple URL formats (management dashboard URL, API URL, etc.) and normalizes them internally. Always store the base URL; `upload_api_url` is derived as `{cpa_base_url}/auth-files`.
