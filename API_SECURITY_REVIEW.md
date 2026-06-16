# API Security Review

## Scope

- `main.py`
- `app/api/upload.py`
- `app/api/query.py`
- `app/utils/zip_handler.py`

## Current Security Posture

- **Authentication:** Production-only API key middleware protects `/api/upload/*` and `/api/query/*`.
- **Rate limiting:** Enabled in production with `slowapi`.
  - Upload routes: `10/hour` per IP
  - Query routes: `120/hour` per IP
- **Upload size limit:** ZIP payloads enforced to 25 MB with `413` rejection.
- **ZIP extraction hardening:** Traversal checks, symlink rejection, entry count and total size limits.
- **CORS:** Strict production origins and relaxed development localhost origins.
- **Security headers:** `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`.

## Findings

### 1) Unauthenticated endpoint risk

- **Status:** Mitigated for public API routes.
- **Notes:** `/health`, `/`, `/docs`, `/openapi.json` remain intentionally unauthenticated.

### 2) Quota/DoS abuse risk

- **Status:** Partially mitigated.
- **Notes:** IP rate limits are present; upstream proxy limits are still recommended (Nginx/Cloudflare).

### 3) ZIP archive attack risk

- **Status:** Mitigated.
- **Notes:** Archive path normalization and extraction limits significantly reduce traversal/ZIP bomb risk.

### 4) Prompt injection risk

- **Status:** Residual.
- **Notes:** Retrieved code can contain adversarial instructions; this is a model-layer risk and should be handled with additional prompt policies if exposure broadens.

## Recommended Next Hardening

1. Add reverse-proxy request throttling and body-size enforcement.
2. Add request logging for abuse detection by IP and session.
3. Consider API key rotation process and periodic key changes.
