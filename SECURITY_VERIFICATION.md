# Security Verification

Verification run after implementing production security layer.

## Environment Modes

- **Development mode (`ENVIRONMENT=development`)**
  - API key auth: disabled
  - Rate limiting: disabled
  - CORS: localhost-friendly (from `ALLOWED_ORIGINS` + localhost regex)
- **Production mode (`ENVIRONMENT=production`)**
  - API key auth: enabled for `/api/upload/*` and `/api/query/*`
  - Rate limiting: enabled via `slowapi`
  - CORS: strict (`https://anikait.page`, `https://www.anikait.page`)

## Test Results

- **Valid API key**
  - Request: `GET /api/query/stats?session_id=s1` with `X-API-Key: super-secret-key`
  - Expected: `200`
  - Actual: `200`
  - Result: PASS

- **Missing API key**
  - Request: `GET /api/query/stats?session_id=s1` without `X-API-Key`
  - Expected: `401 Unauthorized`
  - Actual: `401`
  - Result: PASS

- **Wrong API key**
  - Request: `GET /api/query/stats?session_id=s1` with invalid `X-API-Key`
  - Expected: `401 Unauthorized`
  - Actual: `401`
  - Result: PASS

- **Query rate limit exceeded**
  - Route limit: `120/hour` per IP
  - Test: 121 requests to query endpoint from same client/IP
  - Expected: `429 Too Many Requests`
  - Actual: `429`
  - Result: PASS

- **Upload rate limit exceeded**
  - Route limit: `10/hour` per IP
  - Test: 11 requests to upload endpoint from same client/IP
  - Expected: `429 Too Many Requests`
  - Actual: `429`
  - Result: PASS

- **Large ZIP upload rejected**
  - Limit: `25 MB`
  - Test: `26 MB` file upload to `POST /api/upload/zip`
  - Expected: `413 Payload Too Large`
  - Actual: `413`
  - Result: PASS

## Security Headers Check

Configured globally via middleware:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`

## Outcome

Production security baseline is in place and functioning:

- API key auth protects Gemini-backed endpoints
- Per-IP rate limits protect quota and VPS resources
- ZIP payload size is enforced at 25 MB
- CORS is strict in production and relaxed in development
