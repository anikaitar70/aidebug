# Penetration Testing Report (External Attacker Model)

## Scope

Tested unauthenticated and low-privilege abuse paths for:

- API key theft vectors
- Gemini quota abuse
- ZIP upload/extraction abuse (zip-slip, zip bombs, symlinks)
- Server file read attempts
- Rate-limit and auth bypasses
- Service crash / resource exhaustion paths

Primary code reviewed:

- `main.py`
- `app/api/upload.py`
- `app/api/query.py`
- `app/utils/zip_handler.py`
- `app/utils/config.py`

## Executive Summary

- **Critical finding identified and fixed:** unauthenticated direct access to `POST /query` allowed Gemini usage outside protected API routes.
- **High-risk hardening added:** strict-by-default auth/rate-limit config and session ID format validation to reduce session hijack/bruteforce surface.
- **ZIP handling appears robust** against common archive exploitation patterns (traversal, symlinks, oversized extraction).
- **Residual risk remains** around prompt-injection style LLM manipulation and shared API key operational risk.

## Findings

### 1) Critical: Authentication + rate-limit bypass on `POST /query` (Fixed)

- **Attack path:** external user can call `/query` directly instead of `/api/query/search`.
- **Impact:** bypasses API protection intent and enables Gemini abuse/DoS.
- **Root cause:** auth middleware only protected `/api/upload` and `/api/query`; `/query` was outside this prefix and had no limiter.
- **Fix implemented:**
  - Added `/query` to auth-protected prefixes in `main.py`.
  - Added rate limiting to `/query` via `@limiter.limit("120/hour")`.
  - Switched API key comparison to constant-time `secrets.compare_digest`.
- **Validation evidence:**
  - `GET /health` -> `200`
  - `POST /query` without key -> `401`
  - `POST /api/query/search` without key -> `401`

### 2) High: Insecure defaults disabled protections in non-production mode (Fixed)

- **Attack path:** app started with development defaults had no auth/rate limits.
- **Impact:** easy external abuse if deployed with weak env hygiene.
- **Fix implemented:**
  - Added explicit `AUTH_ENABLED` and `RATE_LIMIT_ENABLED` settings.
  - Set secure defaults (`True`) in `app/utils/config.py`.
  - Documented new env vars in `.env.example`.

### 3) Medium: Session ID enumeration / cross-session abuse risk (Partially fixed)

- **Attack path:** attacker guesses weak session IDs and queries another session's data.
- **Impact:** potential unauthorized context retrieval if IDs are predictable/leaked.
- **Fix implemented:**
  - Added strict `session_id` format validation in:
    - `app/api/upload.py`
    - `app/api/query.py`
  - Allowed pattern: `^[A-Za-z0-9_-]{24,128}$`
- **Residual risk:** format validation improves entropy requirements but does not cryptographically bind sessions to identity.

### 4) Medium: Internal error detail exposure in query failures (Fixed)

- **Attack path:** force server errors and harvest internals from API responses.
- **Impact:** information disclosure to attacker.
- **Fix implemented:** replaced detailed error return with generic `"Query processing failed"` in `app/api/query.py`.

### 5) ZIP exploitation attempts (No critical bypass observed)

- **Tested vectors:**
  - `../` traversal and absolute paths
  - symlink entries
  - excessive entry count
  - oversized extracted content (zip-bomb style)
  - deep path nesting
- **Result:** protections are present in `app/utils/zip_handler.py`; no obvious critical bypass identified in static review.

## Applied Remediations

- Updated `main.py`:
  - protect `/query` in auth middleware
  - constant-time API key compare
  - rate-limit `/query`
- Updated `app/utils/config.py`:
  - `AUTH_ENABLED`, `RATE_LIMIT_ENABLED` flags (secure-by-default)
- Updated `app/api/upload.py` and `app/api/query.py`:
  - strict session ID validation
- Updated `app/api/query.py`:
  - removed internal exception details from HTTP response
- Updated `.env.example`:
  - documented `AUTH_ENABLED`, `RATE_LIMIT_ENABLED`, stronger API key placeholder

## Residual Risks and Recommendations

- Add per-user auth (JWT/OAuth) and bind session data to authenticated identity; shared API key alone is weak for multi-user exposure.
- Add request body size and concurrency limits at reverse proxy level (Nginx/Caddy/Cloud load balancer).
- Add LLM prompt-injection guardrails (system policy hardening, sensitive output redaction rules, and answer safety filters).
- Consider migrating from deprecated `google.generativeai` package to supported `google.genai`.

## Retest Checklist

- [x] Unauthenticated `/query` is blocked
- [x] Unauthenticated `/api/query/*` is blocked
- [x] Health endpoint remains available
- [x] Session IDs must meet entropy/format policy
- [x] Query errors do not leak internal exception text
