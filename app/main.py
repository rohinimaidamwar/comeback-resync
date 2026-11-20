import hashlib
import json
import os
import random
import re
import secrets
import smtplib
import sqlite3
import time
from collections import defaultdict
from contextvars import ContextVar
from email.message import EmailMessage
from typing import List
from fastapi import BackgroundTasks, FastAPI, Request, Form
from pydantic import BaseModel, Field
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app import ai, auth, db
from app import ai_data, evidence
from app import agent, mail_content, practice, upskill
from app import community as community_mod
from app.schemas import (
    JobFit,
    JobMatches,
    JobPosting,
    JournalLine,
    Profile,
    SiteCopy,
    StudyPlan,
)

BASE = os.path.dirname(os.path.abspath(__file__))
app = FastAPI()
db.init()
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")
T = Jinja2Templates(directory=os.path.join(BASE, "templates"))
AI_DOWN = "AI is unavailable right now, so this is a starting point. Edit it by hand and add any skills below."
STAGES = {
    "expecting": "I'm expecting",
    "newborn": "I have a newborn",
    "childcare": "I'm raising or educating my children",
    "caregiving": "I'm caring for a parent or family member",
    "health": "I'm on a health or recovery break",
    "relocating": "I'm relocating or studying",
    "earlycareer": "I'm early in my career, starting again",
    "planning": "I'm planning my return",
}
GOALS = ["A job", "Freelance work", "My own venture"]
T.env.globals.update(
    STAGES=STAGES,
    GOALS=GOALS,
    NAV=[
        ("/journal", "Journal", "notebook"),
        ("/profile", "Profile", "user"),
        ("/jobs", "Jobs", "briefcase"),
        ("/money", "Money", "wallet"),
        ("/community", "Community", "users"),
        ("/upskilling", "Learn", "growth"),
        ("/interview", "Interview", "message"),
    ],
)
# Version tag from the stylesheet's content, so a changed CSS file gets a new URL and browsers refetch it.
with open(os.path.join(BASE, "static", "style.css"), "rb") as _f:
    T.env.globals["css_v"] = hashlib.sha256(_f.read()).hexdigest()[
        :10
    ]  # used by the sign-up form
CARDS = {
    "journal": (
        "Break journal",
        "/journal",
        "Log a small win in a minute.",
        "journal.svg",
    ),
    "profile": (
        "Profile",
        "/profile",
        "Turn your story into a profile.",
        "profile.svg",
    ),
    "jobs": ("Jobs", "/jobs", "Match openings or paste any job.", "jobs.svg"),
    "upskilling": (
        "Upskilling",
        "/upskilling",
        "A study plan and where to study.",
        "learn.svg",
    ),
    "interview": (
        "Interview prep",
        "/interview",
        "Talking points and practice partners.",
        "interview.svg",
    ),
    "site": ("My site", "/site", "Publish a portfolio page.", "site.svg"),
    "money": (
        "Money basics",
        "/money",
        "EPF, tax and leave, with sources.",
        "money.svg",
    ),
    "community": (
        "Community",
        "/community",
        "Meet people at your stage.",
        "community.svg",
    ),
}
# The seven steps of the roadmap. "card" picks the tool from CARDS that the step opens and
# borrows its artwork from; "x", "y" and "side" place its milestone on the road in the SVG.
STEPS = [
    {
        "n": "01",
        "label": "01. REFLECT & PLAN",
        "card": "journal",
        "icon": "notebook",
        "intro": "Start with where you are. Set your stage and what you want next, then write down what you have already done. Small things count.",
        "x": 120,
        "y": 375,
        "side": "up",
    },
    {
        "n": "02",
        "label": "02. UPSKILLING",
        "card": "upskilling",
        "icon": "growth",
        "intro": "Courses, certificates and side projects are the easiest wins to forget. Record them while they are fresh.",
        "x": 260,
        "y": 327,
        "side": "down",
    },
    {
        "n": "03",
        "label": "03. FINANCE & BENEFITS",
        "card": "money",
        "icon": "wallet",
        "intro": "Short cards on provident fund, tax and leave, each one pointing at the official source.",
        "x": 400,
        "y": 313,
        "side": "up",
    },
    {
        "n": "04",
        "label": "04. RESUME REBUILD",
        "card": "profile",
        "icon": "user",
        "intro": "Turn your notes into a profile: a summary, a line about your break, and a skills list with evidence.",
        "x": 540,
        "y": 339,
        "side": "down",
    },
    {
        "n": "05",
        "label": "05. NETWORKING",
        "card": "community",
        "icon": "users",
        "intro": "Meet people at your stage, whatever the reason for your break.",
        "x": 680,
        "y": 322,
        "side": "up",
    },
    {
        "n": "06",
        "label": "06. INTERVIEW PREP",
        "card": "interview",
        "icon": "message",
        "intro": "Practise with talking points for a real job, and with a partner from your community.",
        "x": 800,
        "y": 243,
        "side": "down",
    },
    {
        "n": "07",
        "label": "07. APPLYING TO ROLES",
        "card": "jobs",
        "icon": "briefcase",
        "intro": "Work through sample postings with match scores, and pick the roles you want to apply for.",
        "x": 930,
        "y": 200,
        "side": "up",
    },
]


def roadmap():
    """The steps, each placed on the road and linked to the tool page it belongs to."""
    items = []
    for s in STEPS:
        _, url, _, _ = CARDS[s["card"]]
        w = round(len(s["label"]) * 10.8) + 34  # pill width, in SVG units
        d = 1 if s["side"] == "down" else -1  # badges sit below the road on the dips
        items.append(
            {
                **s,
                "href": url,
                "w": w,
                "px": s["x"] - w / 2,  # pill, badge and icon placement in the SVG
                "py": s["y"] + 122 * d,
                "by": s["y"] + 72 * d,
                "ly1": s["y"] + 8 * d,
                "ly2": s["y"] + 45 * d,
                "ix": s["x"] - w / 2 + 12,
                "lx": s["x"] - w / 2 + 36,
            }
        )
    return items


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


# The scheme the browser actually used. The session cookie is only marked Secure over HTTPS:
# browsers drop a Secure cookie on plain http, which would sign the user straight back out.
# Behind Caddy the request arrives over http, so X-Forwarded-Proto carries the real scheme.
SCHEME = ContextVar("scheme", default="http")


@app.middleware("http")
async def sec(req, nxt):
    SCHEME.set(
        req.headers.get("x-forwarded-proto", req.url.scheme).split(",")[-1].strip()
    )
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
        "select sid, stage, goal, profile, email, name from u where sid=? and email is not null and email != ''",
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
        secure=SCHEME.get() == "https",
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
    background: BackgroundTasks,
    email: str = Form(..., max_length=200),
    password: str = Form(..., max_length=200),
    confirm: str = Form(..., max_length=200),
    name: str = Form("", max_length=40),
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
            "insert into u(sid,stage,goal,email,pw,name) values(?,?,?,?,?,?)",
            (sid, stage, goal, email, auth.hash_pw(password), name.strip()[:40]),
        )
    except sqlite3.IntegrityError:
        return page(
            req,
            "register.html",
            None,
            None,
            err="That email is already registered. Log in instead.",
        )
    if not email.endswith(".invalid"):  # demo accounts never get mail
        background.add_task(send_welcome, email, name.strip()[:40])
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
    agent.forget(u["sid"])
    db.rotate_sid(u["sid"], new_sid)
    return go("/", new_sid)


@app.post("/logout")
def logout(req: Request):
    sid, u = current(req)
    agent.forget(sid)
    if u:  # invalidate the session on the server, not just in the browser
        db.rotate_sid(sid, secrets.token_urlsafe(16))
    r = RedirectResponse("/", 303)
    r.delete_cookie("sid")
    return r


@app.get("/")
def home(req: Request):
    sid, u = current(req)
    if not u:
        return page(req, "index.html", None, None, stages=STAGES, steps=[])
    return page(req, "index.html", sid, u, stages=STAGES, steps=roadmap())


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
            "insert into u(sid,stage,goal,email,pw,name) values(?,?,?,?,?,?)",
            (
                sid,
                "expecting",
                "A job",
                f"demo-{secrets.token_hex(6)}@demo.invalid",
                "!",
                "Priya",
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
    agent.forget(sid)
    for t in ("u", "j", "pg", "memberships", "posts"):
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


def save_journal_entry(sid: str, raw: str) -> str:
    """Rewrite an entry as a resume line, tag its skills, and save it. Returns the saved line."""
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
    line = str(d["line"])[:300]
    db.q(
        "insert into j(sid,raw,line,tags) values(?,?,?,?)",
        (sid, raw, line, json.dumps(tags)),
    )
    return line


@app.post("/journal")
def journal_add(req: Request, raw: str = Form(..., max_length=500)):
    sid, u, r = need(req)
    if r:
        return r
    save_journal_entry(sid, raw)
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


JOB_PICKS = 5  # how many sample postings each visit shows


def job_pool():
    """Sample postings. They are fictional and labelled as samples in the UI."""
    return [JobPosting.model_validate(j).model_dump() for j in load("sample_jobs.json")]


def pick_jobs(pool, rng=random, k=JOB_PICKS):
    """A different random selection each time, so the page never looks the same twice."""
    return rng.sample(pool, min(k, len(pool)))


@app.get("/jobs")
def jobs(req: Request):
    sid, u, r = need(req)
    if r:
        return r
    return page(
        req, "jobs.html", sid, u, jobs=pick_jobs(job_pool()), scores={}, paste=None
    )


@app.post("/jobs/match")
def jobs_match(req: Request, ids: List[int] = Form([])):
    sid, u, r = need(req)
    if r:
        return r
    pool = job_pool()
    wanted = set(ids)
    js = [j for j in pool if j["id"] in wanted] or pick_jobs(pool)
    sk = (u["prof"] or {}).get("skills", [])
    low = {s.lower() for s in sk}
    fb = {
        "matches": [
            {
                "id": j["id"],
                "score": min(95, 40 + 25 * len(low & set(j["tags"]))),
                "why": "Estimated from the skills in your profile.",
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
        else "AI matching is unavailable right now. These are quick estimates from your skills."
    )
    return page(
        req, "jobs.html", sid, u, jobs=js, scores=scores, paste=None, notice=notice
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
    st = community_mod.samples()["stories"]
    return page(
        req,
        "community.html",
        sid,
        u,
        circles=community_mod.circle_cards(sid, u["stage"]),
        stories=st,
        circle_names={k: v[0] for k, v in community_mod.CIRCLES.items()},
        msg=community_mod.MESSAGES.get(req.query_params.get("msg", "")),
    )


@app.post("/community/join")
def community_join(req: Request, circle: str = Form(..., max_length=20)):
    sid, u, r = need(req)
    if r:
        return r
    ok = community_mod.join(sid, circle)
    return go("/community?msg=joined" if ok else "/community", sid)


@app.post("/community/leave")
def community_leave(req: Request, circle: str = Form(..., max_length=20)):
    sid, u, r = need(req)
    if r:
        return r
    ok = community_mod.leave(sid, circle)
    return go("/community?msg=left" if ok else "/community", sid)


@app.get("/community/{circle}")
def community_circle(req: Request, circle: str):
    sid, u, r = need(req)
    if r:
        return r
    if circle not in community_mod.CIRCLES or circle not in community_mod.joined(sid):
        return go("/community?msg=join", sid)
    name, about = community_mod.CIRCLES[circle]
    return page(
        req,
        "community_circle.html",
        sid,
        u,
        slug=circle,
        circle_name=name,
        about=about,
        posts=community_mod.posts(circle, sid),
        members=community_mod.counts().get(circle, 0),
        max_post=community_mod.MAX_POST,
        msg=community_mod.MESSAGES.get(req.query_params.get("msg", "")),
    )


@app.post("/community/{circle}/post")
def community_post(req: Request, circle: str, body: str = Form("", max_length=1000)):
    sid, u, r = need(req)
    if r:
        return r
    if circle not in community_mod.CIRCLES or circle not in community_mod.joined(sid):
        return go("/community?msg=join", sid)
    why = community_mod.problem_with(body)
    if not why and limited("post" + sid, 6, 600):
        why = "toofast"
    if why:
        return go(f"/community/{circle}?msg={why}", sid)
    community_mod.add_post(sid, circle, body)
    return go(f"/community/{circle}?msg=posted", sid)


@app.post("/community/{circle}/post/delete")
def community_post_delete(req: Request, circle: str, post_id: int = Form(...)):
    sid, u, r = need(req)
    if r:
        return r
    community_mod.delete_post(sid, post_id)
    return go(f"/community/{circle}?msg=deleted", sid)


def smtp_configured() -> bool:
    return bool(os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"))


def send_welcome(to: str, name: str) -> bool:
    """Welcome email for a new member. Runs in the background; never breaks sign-up."""
    if not smtp_configured():
        return False
    subject, text, page = mail_content.welcome(name)
    m = EmailMessage()
    m["Subject"] = subject
    m["From"] = os.getenv("SMTP_USER")
    m["To"] = to
    m.set_content(text)
    m.add_alternative(page, subtype="html")
    try:
        port = int(os.getenv("SMTP_PORT", "465"))
        host = os.getenv("SMTP_HOST", "smtpout.secureserver.net")
        with (
            smtplib.SMTP_SSL(host, port, timeout=15)
            if port == 465
            else smtplib.SMTP(host, port, timeout=15)
        ) as smtp:
            if port != 465:
                smtp.starttls()
            smtp.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"))
            smtp.send_message(m)
        return True
    except Exception as e:
        print("Welcome mail error:", type(e).__name__)
        return False


def send_mail(name, email, msg):
    user = os.getenv("SMTP_USER")
    pw = os.getenv("SMTP_PASS")
    subject, text, page = mail_content.build(name, email, msg)
    m = EmailMessage()
    m["Subject"] = subject
    m["From"] = user or "noreply@localhost"
    m["To"] = os.getenv("MAIL_TO") or user or "localhost"
    m["Reply-To"] = mail_content._line(email, 200)
    m.set_content(text)
    m.add_alternative(page, subtype="html")
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


def _upskill_page(req, sid, u, notice=None):
    raw = db.q("select plan from u where sid=?", (sid,))[0]["plan"]
    plan = json.loads(raw) if raw else None
    return page(
        req,
        "upskilling.html",
        sid,
        u,
        plan=plan,
        providers=upskill.providers(),
        notice=notice,
    )


@app.get("/upskilling")
def upskilling(req: Request):
    sid, u, r = need(req)
    if r:
        return r
    return _upskill_page(req, sid, u)


@app.post("/upskilling/plan")
def upskilling_plan(req: Request):
    sid, u, r = need(req)
    if r:
        return r
    sk = (u["prof"] or {}).get("skills", [])
    fb = upskill.fallback_plan(u["goal"])
    d, src = ai.ask(
        upskill.prompt(u["goal"], STAGES.get(u["stage"], u["stage"]), sk),
        fb,
        schema=StudyPlan,
        max_tokens=900,
        allow=allow(sid),
    )
    plan = upskill.clean(d)
    db.q("update u set plan=? where sid=?", (json.dumps(plan), sid))
    notice = (
        None
        if src == "ai"
        else "AI is unavailable right now, so this is a starter plan for your goal."
    )
    return _upskill_page(req, sid, u, notice)


@app.post("/upskilling/toggle")
def upskilling_toggle(req: Request, week: int = Form(...), task: int = Form(...)):
    sid, u, r = need(req)
    if r:
        return r
    raw = db.q("select plan from u where sid=?", (sid,))[0]["plan"]
    if raw:
        plan = json.loads(raw)
        try:
            item = plan["weeks"][week]["tasks"][task]
            item["done"] = not item.get("done", False)
            db.q("update u set plan=? where sid=?", (json.dumps(plan), sid))
        except (IndexError, KeyError, TypeError):
            pass  # stale form: ignore
    return go("/upskilling", sid)


VALID_TABS = {"peer", "talk", "ai"}


def _interview_page(req, sid, u, paste=None, notice=None, tab=None):
    rec = practice.record(
        db.q("select practice from u where sid=?", (sid,))[0]["practice"]
    )
    want, can = practice.flags(rec)
    reqs = practice.requests(rec)
    return page(
        req,
        "interview.html",
        sid,
        u,
        paste=paste,
        notice=notice,
        tab=tab if tab in VALID_TABS else "peer",
        me=rec,
        want=want,
        can=can,
        pool=practice.pool(sid, rec),
        pending=reqs,
        requested={r["key"] for r in reqs},
        session_types=practice.SESSION_TYPES,
    )


@app.get("/interview")
def interview(req: Request):
    sid, u, r = need(req)
    if r:
        return r
    return _interview_page(req, sid, u, tab=req.query_params.get("tab"))


@app.post("/interview/paste")
def interview_paste(req: Request, jd: str = Form(..., max_length=6000)):
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
        return _interview_page(
            req,
            sid,
            u,
            notice="AI scoring is unavailable right now. Try again in a moment.",
            tab="talk",
        )
    return _interview_page(req, sid, u, paste=d, tab="talk")


def _save_practice(sid, rec):
    db.q("update u set practice=? where sid=?", (json.dumps(rec), sid))


@app.post("/interview/practice")
def interview_practice(
    req: Request,
    role: str = Form("", max_length=60),
    years: int = Form(0, ge=0, le=40),
    want_interview: str = Form(""),
    can_interview: str = Form(""),
):
    sid, u, r = need(req)
    if r:
        return r
    rec = practice.record(
        db.q("select practice from u where sid=?", (sid,))[0]["practice"]
    )
    rec.pop("opt_in", None)  # replaced by the two intents
    rec.update(
        role=role.strip()[:60],
        years=years,
        want_interview=want_interview == "yes",
        can_interview=can_interview == "yes",
    )
    _save_practice(sid, rec)
    return go("/interview?tab=peer", sid)


@app.post("/interview/request")
def interview_request(
    req: Request,
    partner: str = Form(..., max_length=120),
    session: str = Form("swap", max_length=20),
):
    sid, u, r = need(req)
    if r:
        return r
    rec = practice.record(
        db.q("select practice from u where sid=?", (sid,))[0]["practice"]
    )
    shown = {p["key"] for p in practice.pool(sid, rec)}
    existing = practice.requests(rec)
    # Only people in the pool can be requested, and each person only once.
    if partner in shown and partner not in {x["key"] for x in existing}:
        kind = session if session in practice.SESSION_TYPES else "swap"
        rec["requests"] = (
            [{"key": x["key"], "type": x["type"]} for x in existing]
            + [{"key": partner, "type": kind}]
        )[-10:]
        _save_practice(sid, rec)
    return go("/interview?tab=peer", sid)


@app.post("/interview/request/remove")
def interview_request_remove(req: Request, partner: str = Form(..., max_length=120)):
    sid, u, r = need(req)
    if r:
        return r
    rec = practice.record(
        db.q("select practice from u where sid=?", (sid,))[0]["practice"]
    )
    rec["requests"] = [
        {"key": x["key"], "type": x["type"]}
        for x in practice.requests(rec)
        if x["key"] != partner
    ]
    _save_practice(sid, rec)
    return go("/interview?tab=peer", sid)


# ---- Comeback Buddy (tool-calling chat) ------------------------------------------------------


class AskIn(BaseModel):
    message: str = Field(min_length=1, max_length=600)


class PendingIn(BaseModel):
    id: str = Field(min_length=1, max_length=64)


def _ask_tools(u):
    """What the agent may read. Each tool only sees the signed-in user's own data."""

    def get_profile():
        prof = u["prof"]
        if not prof:
            return {"profile": None}
        return {
            "summary": prof.get("summary", ""),
            "break_statement": prof.get("brk", ""),
            "skills": prof.get("skills", []),
            "goal": u["goal"],
            "stage": STAGES.get(u["stage"], u["stage"]),
        }

    def list_jobs():
        keys = (
            "id",
            "title",
            "company",
            "location",
            "returner_friendly",
            "tags",
            "summary",
        )
        return {"sample_jobs": [{k: j[k] for k in keys} for j in job_pool()]}

    def get_study_plan():
        raw = db.q("select plan from u where sid=?", (u["sid"],))[0]["plan"]
        return json.loads(raw) if raw else {"plan": None}

    return {
        "get_profile": get_profile,
        "list_jobs": list_jobs,
        "get_study_plan": get_study_plan,
    }


def _json_user(req):
    sid, u = current(req)
    return (sid, u) if u else (None, None)


@app.get("/ask")
def ask_page(req: Request):
    sid, u, r = need(req)
    if r:
        return r
    return page(req, "ask.html", sid, u)


@app.post("/ask/send")
def ask_send(req: Request, body: AskIn):
    sid, u = _json_user(req)
    if not u:
        return JSONResponse({"error": "login"}, status_code=401)
    if not os.getenv("ANTHROPIC_API_KEY") or not allow(sid):
        return JSONResponse({"reply": agent.UNAVAILABLE, "steps": [], "pending": None})
    try:
        return JSONResponse(agent.run(sid, body.message, _ask_tools(u)))
    except Exception as e:  # timeouts, API errors: a plain message, never a stack trace
        print("Agent error:", type(e).__name__)
        return JSONResponse({"reply": agent.UNAVAILABLE, "steps": [], "pending": None})


@app.post("/ask/confirm")
def ask_confirm(req: Request, body: PendingIn):
    sid, u = _json_user(req)
    if not u:
        return JSONResponse({"error": "login"}, status_code=401)
    text = agent.confirm(sid, body.id)
    if not text:
        return JSONResponse({"ok": False, "error": "That confirmation has expired."})
    return JSONResponse({"ok": True, "line": save_journal_entry(sid, text)})


@app.post("/ask/cancel")
def ask_cancel(req: Request, body: PendingIn):
    sid, u = _json_user(req)
    if not u:
        return JSONResponse({"error": "login"}, status_code=401)
    return JSONResponse({"ok": agent.cancel(sid, body.id)})
