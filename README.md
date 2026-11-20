# hercomeback
A journey app for women who are expecting, new mothers, or returning from a career break. FastAPI + Jinja2 + SQLite + Claude.

## Run locally
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env   # add ANTHROPIC_API_KEY (without it, demo responses are used)
    uvicorn app.main:app --reload
Open http://localhost:8000 and click "Load demo persona". Emails go to db/outbox.txt until SMTP is set.

## Deploy (GoDaddy VPS)
1. Install Docker on the VPS, copy this folder, and `cp .env.example .env`. Fill in DOMAIN, the API key and the SMTP values.
2. Point the domain's A record at the VPS IP.
3. `docker compose up -d --build`. Caddy gets the HTTPS certificate automatically.
4. Check https://yourdomain.com/health, then send a test message from /contact.
If SMTP login fails, try port 587 (STARTTLS) or host smtp.titan.email.

## Before submitting
- Fill data/jobs.json and data/finance.json with real entries and official source URLs, and set "verified": true.
- Pin dependency versions, and never commit .env.

## Not built yet (roadmap)
Handover document, pitch drafts, Hindi/Marathi, domain suggestions, an AI mock interview, and scheduling between practice partners. Comeback Buddy (a tool-calling chat that can propose journal entries for the user to confirm) is built.
