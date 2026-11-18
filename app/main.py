import json
import os
import re
import secrets
import smtplib
import sqlite3
import time
from collections import defaultdict
from email.message import EmailMessage
from typing import List
from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app import ai, auth, db
from app import ai_data, evidence
from app.schemas import JobFit, JobMatches, JournalLine, Profile, SiteCopy

BASE = os.path.dirname(os.path.abspath(__file__))
app = FastAPI()
db.init()
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")
T = Jinja2Templates(directory=os.path.join(BASE, "templates"))
AI_DOWN = "AI is unavailable right now, so this is a starting point. Edit it by hand and add any skills below."
STAGES = {
    "expecting": "I'm expecting",
    "newborn": "I have a newborn",
    "planning": "I'm planning my return",
}
GOALS = ["A job", "Freelance work", "My own venture"]
T.env.globals.update(STAGES=STAGES, GOALS=GOALS)  # used by the sign-up form
CARDS = {
    "journal": ("Break journal", "/journal", "Log a small win in a minute."),
    "profile": ("Profile", "/profile", "Turn your story into a profile."),
    "jobs": ("Jobs", "/jobs", "Match openings or paste any job."),
    "site": ("My site", "/site", "Publish a portfolio page."),
    "money": ("Money basics", "/money", "EPF, tax and leave, with sources."),
    "community": ("Community", "/community", "Meet people at your stage."),
}
ORDER = {
    "expecting": ["money", "journal", "community", "profile"],
    "newborn": ["journal", "community", "money", "profile"],
    "planning": ["profile", "jobs", "site", "journal", "money", "community"],
}
HITS = defaultdict(list)


def limited(key, n=5, w=600):
    now = time.time()
    HITS[key] = [t for t in HITS[key] if now - t < w]
    if len(HITS[key]) >= n:
        return True
    HITS[key].append(now)
    return False


def ip(req):
    # Caddy appends the real client IP as the last X-Forwarded-For entry. Earlier entries
    # come from the client and can be spoofed, so only the last one is trusted.
    xff = req.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[-1].strip()
    return req.client.host if req.client else "?"


@app.middleware("http")
async def sec(req, nxt):
    r = await nxt(req)
    r.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "same-origin",
            "Content-Security-Policy": "default-src 'self'; form-action 'self'",
        }
    )
    return r


MAX_BODY = (
    64 * 1024
)  # forms are capped well below this; anything bigger is rejected early


@app.middleware("http")
async def body_limit(req, nxt):
    n = req.headers.get("content-length")
    if (
        req.method in ("POST", "PUT", "PATCH")
        and n
        and n.isdigit()
        and int(n) > MAX_BODY
    ):
        return PlainTextResponse("Request too large.", 413)
    return await nxt(req)


def current(req):
    sid = req.cookies.get("sid")
    if not sid:
        return None, None
    # The password hash is never loaded for normal pages.
    rows = db.q(
        "select sid, stage, goal, profile, email from u where sid=? and email is not null and email != ''",
        (sid,),
    )
    if not rows:
        return None, None
    u = rows[0]
    u["prof"] = json.loads(u["profile"]) if u["profile"] else None
    return sid, u


def need(req):
    sid, u = current(req)
    if u:
        return sid, u, None
    return None, None, RedirectResponse("/login", 303)


def _cookie(r, sid):
    r.set_cookie(
        "sid",
        sid,
        httponly=True,
        samesite="lax",
        max_age=2592000,
        secure=os.getenv("COOKIE_SECURE") == "1",
    )
    return r


def page(req, name, sid, u, **x):
    r = T.TemplateResponse(req, name, {"u": u, "prof": (u or {}).get("prof"), **x})
    return _cookie(r, sid) if sid else r


def go(url, sid=None):
    r = RedirectResponse(url, 303)
    return _cookie(r, sid) if sid else r


def load(n):
    return json.load(open(os.path.join(BASE, "..", "data", n)))


def allow(sid):
    return not limited("ai" + sid, 40, 86400)


def lines(sid):
    return [
        r["line"] for r in db.q("select line from j where sid=? order by id", (sid,))
    ]


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/register")
def register_get(req: Request):
    sid, u = current(req)
    if u:
        return go("/", sid)
    return page(req, "register.html", None, None, err=None)


@app.post("/register")
def register_post(
    req: Request,
    email: str = Form(..., max_length=200),
    password: str = Form(..., max_length=200),
    confirm: str = Form(..., max_length=200),
    stage: str = Form("planning", max_length=20),
    goal: str = Form("A job", max_length=40),
):
    if limited("reg" + ip(req), 8, 600):
        return page(
            req, "register.html", None, None, err="Too many tries. Wait a few minutes."
        )
    email = auth.norm_email(email)
    if not auth.valid_email(email):
        return page(req, "register.html", None, None, err="Enter a valid email.")
    if len(password) < 8:
        return page(
            req,
            "register.html",
            None,
            None,
            err="Password must be at least 8 characters.",
        )
    if password != confirm:
        return page(req, "register.html", None, None, err="Passwords do not match.")
    sid = secrets.token_urlsafe(16)
    try:
        stage = stage if stage in STAGES else "planning"
        goal = goal if goal in GOALS else "A job"
        db.q(
            "insert into u(sid,stage,goal,email,pw) values(?,?,?,?,?)",
            (sid, stage, goal, email, auth.hash_pw(password)),
        )
    except sqlite3.IntegrityError:
        return page(
            req,
            "register.html",
            None,
            None,
            err="That email is already registered. Log in instead.",
        )
    return go("/", sid)


@app.get("/login")
def login_get(req: Request):
    sid, u = current(req)
    if u:
        return go("/", sid)
    return page(req, "login.html", None, None, err=None)


@app.post("/login")
def login_post(
    req: Request,
    email: str = Form(..., max_length=200),
    password: str = Form(..., max_length=200),
):
    if limited("login" + ip(req), 10, 600):
        return page(
            req, "login.html", None, None, err="Too many tries. Wait a few minutes."
        )
    email = auth.norm_email(email)
    rows = db.q("select * from u where email=?", (email,)) if email else []
    u = rows[0] if rows else None
    if not u or not u.get("pw") or not auth.check_pw(password, u["pw"]):
        return page(req, "login.html", None, None, err="Email or password is wrong.")
    # New session token on every login, so an old copy of the cookie stops working.
    new_sid = secrets.token_urlsafe(16)
    db.q("update u set sid=? where sid=?", (new_sid, u["sid"]))
    return go("/", new_sid)


@app.post("/logout")
def logout(req: Request):
    sid, u = current(req)
    if u:  # invalidate the session on the server, not just in the browser
        db.q("update u set sid=? where sid=?", (secrets.token_urlsafe(16), sid))
    r = RedirectResponse("/", 303)
    r.delete_cookie("sid")
    return r


@app.get("/")
def home(req: Request):
    sid, u = current(req)
    if not u:
        return page(req, "index.html", None, None, stages=STAGES, cards=[])
    cards = [CARDS[k] for k in ORDER.get(u["stage"], ORDER["planning"])]
    return page(req, "index.html", sid, u, stages=STAGES, cards=cards)


@app.post("/stage")
def stage(req: Request, stage: str = Form(...), goal: str = Form(..., max_length=40)):
    sid, u, r = need(req)
    if r:
        return r
    if stage in STAGES:
        db.q(
            "update u set stage=?, goal=? where sid=?",
            (stage, goal if goal in GOALS else u["goal"], sid),
        )
    return go("/", sid)


@app.post("/demo")
def demo(req: Request):
    sid, u = current(req)
    if not u:
        # Anyone can start the demo without registering. The account gets a random email
        # and an unusable password hash, so nobody can log in to it directly.
        if limited("demo" + ip(req), 10, 600):
            return go("/login")
        sid = secrets.token_urlsafe(16)
        db.q(
            "insert into u(sid,stage,goal,email,pw) values(?,?,?,?,?)",
            (
                sid,
                "expecting",
                "A job",
                f"demo-{secrets.token_hex(6)}@demo.invalid",
                "!",
            ),
        )
    p = {
        "summary": "Priya, a product manager with 6 years in fintech, leading roadmaps and cross-functional teams.",
        "brk": "Planned maternity leave, using the time to mentor and upskill.",
        "skills": [
            "Product roadmapping",
            "Stakeholder management",
            "Mentoring",
            "Data analysis",
        ],
    }
    db.q(
        "update u set stage='expecting', goal='A job', profile=? where sid=?",
        (json.dumps(p), sid),
    )
    db.q("delete from j where sid=?", (sid,))
    for line in [
        "Mentored two junior product managers through their first launches.",
        "Completed an online course in data analysis.",
    ]:
        db.q("insert into j(sid,raw,line) values(?,?,?)", (sid, line, line))
    return go("/", sid)


@app.post("/delete")
def delete(req: Request):
    sid, u, r = need(req)
    if r:
        return r
    for t in ("u", "j", "pg"):
        db.q(f"delete from {t} where sid=?", (sid,))
    r = RedirectResponse("/", 303)
    r.delete_cookie("sid")
    return r


@app.get("/journal")
def journal(req: Request):
    sid, u, r = need(req)
    if r:
        return r
    entries = db.q("select raw,line,tags from j where sid=? order by id desc", (sid,))
    for e in entries:
        e["tags"] = json.loads(e["tags"] or "[]")
    return page(req, "journal.html", sid, u, entries=entries)


@app.post("/journal")
def journal_add(req: Request, raw: str = Form(..., max_length=500)):
    sid, u, r = need(req)
    if r:
        return r
    d, _ = ai.ask(
        f"Rewrite as one resume-ready line using only these facts. Also list up to 5 skills clearly shown in the entry. "
        f'JSON {{"line": str, "skills": [str]}}.\n{ai_data.data(raw)}',
        {"line": raw, "skills": []},
        schema=JournalLine,
        model=ai.FAST,
        max_tokens=200,
        allow=allow(sid),
    )
    tags = [str(t)[:40] for t in d["skills"][:5]]
    db.q(
        "insert into j(sid,raw,line,tags) values(?,?,?,?)",
        (sid, raw, str(d["line"])[:300], json.dumps(tags)),
    )
    return go("/journal", sid)


@app.get("/profile")
def profile(req: Request):
    sid, u, r = need(req)
    if r:
        return r
    return page(req, "profile.html", sid, u, draft=None)


@app.post("/profile")
def profile_gen(req: Request, text: str = Form(..., max_length=6000)):
    sid, u, r = need(req)
    if r:
        return r
    prompt = (
        f'Goal: {u["goal"]}. Return JSON {{"summary": str, "break_statement": str, "skills": [{{"name": str, "evidence": str}}]}}. '
        f'Every skill needs "evidence": a short quote copied word for word from the text or journal below. '
        f"Skip any skill you cannot quote.\n{ai_data.data(text)}\nJournal:\n"
        + ai_data.data(
            "\n".join(
                r["raw"]
                for r in db.q("select raw from j where sid=? order by id", (sid,))
            )
        )
    )
    # Fallback only uses the user's own words. It never invents a skill.
    fb = {"summary": text[:200], "break_statement": "", "skills": []}
    d, src = ai.ask(prompt, fb, schema=Profile, allow=allow(sid))
    # Honesty rule, checked on the server: keep only skills backed by the user's own words.
    sources = [text] + [r["raw"] for r in db.q("select raw from j where sid=?", (sid,))]
    skills = [s for s in d["skills"] if isinstance(s, dict) and "name" in s][:12]
    d["skills"], removed = evidence.keep_supported(skills, sources)
    notes = [AI_DOWN] if src != "ai" else []
    if removed:
        notes.append(
            f"{removed} suggested skill(s) were removed because their evidence is not in what you wrote."
        )
    return page(req, "profile.html", sid, u, draft=d, notice=" ".join(notes) or None)


@app.post("/profile/save")
def profile_save(
    req: Request,
    summary: str = Form(..., max_length=600),
    brk: str = Form("", max_length=300),
    skills: List[str] = Form([]),
    extra: str = Form("", max_length=300),
):
    sid, u, r = need(req)
    if r:
        return r
    # Skills typed by hand by the user are user-provided, so they are accepted as-is.
    skills = skills + [s.strip() for s in extra.split(",") if s.strip()]
    db.q(
        "update u set profile=? where sid=?",
        (
            json.dumps(
                {
                    "summary": summary,
                    "brk": brk,
                    "skills": [s[:60] for s in skills[:20]],
                }
            ),
            sid,
        ),
    )
    return go("/profile", sid)


@app.get("/jobs")
def jobs(req: Request):
    sid, u, r = need(req)
    if r:
        return r
    return page(req, "jobs.html", sid, u, jobs=load("jobs.json"), scores={}, paste=None)


@app.post("/jobs/match")
def jobs_match(req: Request):
    sid, u, r = need(req)
    if r:
        return r
    js = load("jobs.json")
    sk = (u["prof"] or {}).get("skills", [])
    low = {s.lower() for s in sk}
    fb = {
        "matches": [
            {
                "id": j["id"],
                "score": min(95, 40 + 25 * len(low & set(j["tags"]))),
                "why": "Matched on keywords in your skills.",
            }
            for j in js
        ]
    }
    d, src = ai.ask(
        f"Profile skills: {ai_data.data(sk)}. Score each job 0-100 for fit with a one-sentence reason, noting gap-friendly signals. "
        f'JSON {{"matches": [{{"id": int, "score": int, "why": str}}]}}. Jobs: {ai_data.data(json.dumps(js))}',
        fb,
        schema=JobMatches,
        allow=allow(sid),
    )
    scores = {m["id"]: m for m in d["matches"] if isinstance(m, dict) and "id" in m}
    notice = (
        None
        if src == "ai"
        else "AI is unavailable right now, so these scores come from keyword matching."
    )
    return page(
        req, "jobs.html", sid, u, jobs=js, scores=scores, paste=None, notice=notice
    )


@app.post("/jobs/paste")
def jobs_paste(req: Request, jd: str = Form(..., max_length=6000)):
    sid, u, r = need(req)
    if r:
        return r
    sk = (u["prof"] or {}).get("skills", [])
    fb = {"score": 0, "why": "", "talking_points": []}
    d, src = ai.ask(
        f'Skills: {ai_data.data(sk)}. Rate fit for the job in the data tags. JSON {{"score": int, "why": str, "talking_points": [str]}}\n{ai_data.data(jd)}',
        fb,
        schema=JobFit,
        allow=allow(sid),
    )
    if src != "ai":  # never show a 0% score when the AI did not run
        return page(
            req,
            "jobs.html",
            sid,
            u,
            jobs=load("jobs.json"),
            scores={},
            paste=None,
            notice="AI scoring is unavailable right now. Try again in a moment.",
        )
    return page(
        req,
        "jobs.html",
        sid,
        u,
        jobs=load("jobs.json"),
        scores={},
        paste=d,
        notice=None,
    )


@app.get("/site")
def site(req: Request):
    sid, u, r = need(req)
    if r:
        return r
    return page(
        req,
        "site.html",
        sid,
        u,
        draft=None,
        pub=db.q("select slug from pg where sid=? and live=1", (sid,)),
        err=req.query_params.get("err"),
    )


@app.post("/site/preview")
def site_preview(req: Request):
    sid, u, r = need(req)
    if r:
        return r
    if not u["prof"]:
        return go("/profile", sid)
    p = u["prof"]
    fb = {
        "headline": "Hello, I'm back.",
        "about": p["summary"],
        "services": p["skills"][:4],
    }
    d, src = ai.ask(
        f'Write portfolio website copy using only this profile: {ai_data.data(json.dumps(p))}. JSON {{"headline": str, "about": str, "services": [str]}}',
        fb,
        schema=SiteCopy,
        allow=allow(sid),
    )
    c = {
        "headline": str(d["headline"])[:120],
        "about": str(d["about"])[:800],
        "services": [str(s)[:80] for s in d["services"][:5]],
    }
    return page(
        req,
        "site.html",
        sid,
        u,
        draft=c,
        draft_json=json.dumps(c),
        pub=[],
        err=None,
        notice=None if src == "ai" else AI_DOWN,
    )


@app.post("/site/publish")
def site_publish(
    req: Request,
    slug: str = Form(...),
    content: str = Form(..., max_length=4000),
    confirm: str = Form(""),
):
    sid, u, r = need(req)
    if r:
        return r
    try:
        c = json.loads(content)
        c = {
            "headline": str(c["headline"])[:120],
            "about": str(c["about"])[:800],
            "services": [str(s)[:80] for s in c["services"][:5]],
        }
    except Exception:
        return go("/site?err=bad", sid)
    if confirm != "yes" or not re.fullmatch(r"[a-z0-9-]{3,30}", slug):
        return go("/site?err=bad", sid)
    own = db.q("select sid from pg where slug=?", (slug,))
    if own and own[0]["sid"] != sid:
        return go("/site?err=taken", sid)
    db.q(
        "insert or replace into pg(slug,sid,content,live) values(?,?,?,1)",
        (slug, sid, json.dumps(c)),
    )
    return go("/site", sid)


@app.post("/site/unpublish")
def site_unpublish(req: Request):
    sid, u, r = need(req)
    if r:
        return r
    db.q("update pg set live=0 where sid=?", (sid,))
    return go("/site", sid)


@app.get("/p/{slug}")
def portfolio(req: Request, slug: str):
    sid, u = current(req)
    rec = db.q("select content from pg where slug=? and live=1", (slug,))
    if not rec:
        return HTMLResponse("Page not found", 404)
    return page(req, "portfolio.html", sid, u, c=json.loads(rec[0]["content"]))


@app.get("/money")
def money(req: Request):
    sid, u = current(req)
    return page(req, "money.html", sid, u, cards=load("finance.json"))


@app.get("/community")
def community(req: Request):
    sid, u, r = need(req)
    if r:
        return r
    return page(req, "community.html", sid, u)


def send_mail(name, email, msg):
    def clean(s):
        return re.sub(r"[\r\n]+", " ", s)

    m = EmailMessage()
    user = os.getenv("SMTP_USER")
    pw = os.getenv("SMTP_PASS")
    m["Subject"] = "Comeback contact: " + clean(name)[:50]
    m["From"] = user or "noreply@localhost"
    m["To"] = os.getenv("MAIL_TO") or user or "localhost"
    m["Reply-To"] = clean(email)
    m.set_content(f"From: {clean(name)} <{clean(email)}>\n\n{msg}")
    if not (user and pw):
        # SMTP not configured: keep a local copy for development, but report it as not sent.
        os.makedirs("db", exist_ok=True)
        open("db/outbox.txt", "a").write(str(m) + "\n---\n")
        return False
    port = int(os.getenv("SMTP_PORT", "465"))
    host = os.getenv("SMTP_HOST", "smtpout.secureserver.net")
    with (
        smtplib.SMTP_SSL(host, port, timeout=15)
        if port == 465
        else smtplib.SMTP(host, port, timeout=15)
    ) as s:
        if port != 465:
            s.starttls()
        s.login(user, pw)
        s.send_message(m)
    return True


CONTACT_ERRORS = {
    "limit": "You have sent several messages recently. Please try again later.",
    "email": "Please enter a valid email address.",
    "mail": "We could not send your message right now. Please try again later.",
}


@app.get("/contact")
def contact(req: Request):
    sid, u = current(req)
    err = CONTACT_ERRORS.get(req.query_params.get("err"))
    return page(req, "contact.html", sid, u, sent=req.query_params.get("sent"), err=err)


@app.post("/contact")
def contact_send(
    req: Request,
    name: str = Form(..., max_length=100),
    email: str = Form(..., max_length=200),
    message: str = Form(..., max_length=3000),
    website: str = Form(""),
):
    sid, u = current(req)
    if website:  # honeypot: bots get a success page, nothing is sent
        return go("/contact?sent=1", sid)
    if limited(ip(req)):
        return go("/contact?err=limit", sid)
    if not auth.valid_email(auth.norm_email(email)):
        return go("/contact?err=email", sid)
    try:
        sent = send_mail(name, email, message)
    except Exception as e:
        print("Mail error:", type(e).__name__)
        sent = False
    return go("/contact?sent=1" if sent else "/contact?err=mail", sid)


@app.get("/privacy")
def privacy(req: Request):
    sid, u = current(req)
    return page(req, "privacy.html", sid, u)
