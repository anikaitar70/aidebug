# GitHub Release Checklist

## Final Security Verification

- [x] No real API keys remain in tracked config files
- [x] No private tokens or OAuth secrets found in source/config/docs
- [x] `.env` sanitized for public release
- [x] `.env.example` contains placeholders only
- [x] `.gitignore` blocks env files, logs, caches, uploads, and build artifacts
- [x] ZIP extraction hardened against traversal/symlink/archive abuse
- [ ] Auth/rate-limits implemented for all public endpoints

## Pass/Fail Status

- **Secrets exposure:** PASS
- **Public repo hygiene:** PASS
- **ZIP upload safety:** PASS
- **API abuse resistance (auth/quota/rate limits):** FAIL (needs implementation or gateway policy)
- **OVH deployment documentation:** PASS

## Required Before Public Launch

1. Revoke/rotate any previously exposed Google API key.
2. Add authentication to upload/query endpoints or enforce strict API gateway controls.
3. Apply rate limits (Nginx/Cloudflare and/or app middleware).
4. Re-run secret scan before first push.
