# OVH VPS Deployment Guide

## 1) Server Preparation

- Provision Ubuntu 22.04+ VPS on OVH
- Create non-root deploy user
- Configure firewall (`ufw`) for `22`, `80`, `443`
- Install Docker and Docker Compose plugin

## 2) App Configuration

- Copy project to server
- Create production `.env` from `.env.example`
- Set strong production values:
  - `DEBUG=False`
  - `GOOGLE_API_KEY=<real-secret-on-server-only>`
  - restrictive `ALLOWED_ORIGINS`

## 3) Run with Docker Compose

- Build and run:
  - `docker compose up -d --build`
- Verify health:
  - `curl http://127.0.0.1:8000/health`

## 4) Reverse Proxy (Nginx)

- Route public domain to app container (`127.0.0.1:8000`)
- Enforce HTTPS using Let's Encrypt (`certbot`)
- Add request size limits and timeouts

Recommended Nginx hardening:

- `client_max_body_size 20m;`
- request rate limiting on upload/query routes
- security headers (HSTS, X-Content-Type-Options, X-Frame-Options)

## 5) Operational Hardening

- Restrict CORS to trusted frontend origins
- Enable log rotation
- Set resource limits (CPU/RAM) in compose
- Monitor 4xx/5xx spikes and upload abuse patterns
- Back up only required persistent data

## 6) Update Procedure

- Pull latest code to a staging folder
- Rebuild image
- Run smoke tests (`/health`, one ZIP upload/process cycle, one `/api/query/search` request)
- Swap traffic after validation
