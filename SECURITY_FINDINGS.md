# Security Findings

## 1) Exposed API key in environment file

- **Severity:** Critical
- **File path:** `.env`
- **Reason:** `GOOGLE_API_KEY` contained a real key value. If committed publicly, this allows unauthorized API usage and billing abuse.
- **Recommended fix:** Replace with placeholder immediately, rotate/revoke the old key in Google Cloud, and keep real values only in untracked local/secret manager storage.
- **Status:** Fixed in repository (`GOOGLE_API_KEY=your_google_api_key_here`).

## 2) ZIP extraction abuse surface (pre-fix)

- **Severity:** High
- **File path:** `app/utils/zip_handler.py`
- **Reason:** ZIP logic lacked strong guardrails for symlink entries, total uncompressed size limits, entry count caps, and path depth limits (common ZIP bomb/path abuse vectors).
- **Recommended fix:** Enforce strict archive limits, reject symlinks, block suspicious paths, and extract with controlled streaming.
- **Status:** Fixed with archive safety limits and safe extraction.

## 3) Upload ID path safety

- **Severity:** High
- **File path:** `app/api/upload.py`
- **Reason:** `upload_id` from request was used to build filesystem paths without strict format validation, increasing path traversal risk.
- **Recommended fix:** Validate with strict allowlist pattern and resolve only under system temp directory.
- **Status:** Fixed via `UPLOAD_ID_PATTERN` validation.

## 4) Internal path disclosure

- **Severity:** Medium
- **File path:** `app/api/upload.py`
- **Reason:** ZIP response included `temp_directory`, exposing internal server filesystem paths.
- **Recommended fix:** Remove absolute path fields from API responses.
- **Status:** Fixed (`temp_directory` removed).

## 5) Missing authentication/rate limiting (architectural risk)

- **Severity:** Medium
- **File path:** `app/api/query.py`, `app/api/upload.py`, `main.py`
- **Reason:** Endpoints are session-based but unauthenticated; abuse (spam uploads/query flooding) is possible on public deployments.
- **Recommended fix:** Add API auth (token/JWT), per-IP/per-session rate limits, and gateway-level controls (Nginx/Cloudflare).
- **Status:** Not fully fixed in codebase; documented for deployment hardening.
