import json, os, re, secrets, smtplib, sqlite3, time
from collections import defaultdict
from email.message import EmailMessage
from typing import List
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app import ai, auth, db

BASE = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(); db.init()
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")
T = Jinja2Templates(directory=os.path.join(BASE, "templates"))
STAGES = {"expecting": "I'm expecting", "newborn": "I have a newborn", "planning": "I'm planning my return"}
CARDS = {"journal": ("Break journal", "/journal", "Log a small win in a minute."),
         "profile": ("Profile", "/profile", "Turn your story into a profile."),
         "jobs": ("Jobs", "/jobs", "Match openings or paste any job."),
         "site": ("My site", "/site", "Publish a portfolio page."),
         "money": ("Money basics", "/money", "EPF, tax and leave, with sources."),
         "community": ("Community", "/community", "Meet people at your stage.")}
ORDER = {"expecting": ["money", "journal", "community", "profile"],
         "newborn": ["journal", "community", "money", "profile"],
         "planning": ["profile", "jobs", "site", "journal", "money", "community"]}
HITS = defaultdict(list)

def limited(key, n=5, w=600):
    now = time.time(); HITS[key] = [t for t in HITS[key] if now - t < w]
    if len(HITS[key]) >= n: return True
    HITS[key].append(now); return False

def ip(req):
    return req.headers.get("x-forwarded-for", req.client.host if req.client else "?").split(",")[0].strip()

@app.middleware("http")
async def sec(req, nxt):
    r = await nxt(req)
    r.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "same-origin",
                      "Content-Security-Policy": "default-src 'self'; form-action 'self'"})
    return r

def current(req):
    sid = req.cookies.get("sid")
    if not sid: return None, None
    rows = db.q("select * from u where sid=? and email is not null and email != ''", (sid,))
    if not rows: return None, None
    u = rows[0]
    u["prof"] = json.loads(u["profile"]) if u["profile"] else None
    return sid, u

def need(req):
    sid, u = current(req)
    if u: return sid, u, None
    return None, None, RedirectResponse("/login", 303)

def _cookie(r, sid):
    r.set_cookie("sid", sid, httponly=True, samesite="lax", max_age=2592000, secure=os.getenv("COOKIE_SECURE") == "1"); return r
def page(req, name, sid, u, **x):
    r = T.TemplateResponse(req, name, {"u": u, "prof": (u or {}).get("prof"), **x})
    return _cookie(r, sid) if sid else r
def go(url, sid=None):
    r = RedirectResponse(url, 303)
    return _cookie(r, sid) if sid else r
def load(n): return json.load(open(os.path.join(BASE, "..", "data", n)))
def allow(sid): return not limited("ai" + sid, 40, 86400)
def lines(sid): return [r["line"] for r in db.q("select line from j where sid=? order by id", (sid,))]

@app.get("/health")
def health(): return {"ok": True}

@app.get("/register")
def register_get(req: Request):
    sid, u = current(req)
    if u: return go("/", sid)
    return page(req, "register.html", None, None, err=None)

@app.post("/register")
def register_post(req: Request, email: str = Form(..., max_length=200), password: str = Form(..., max_length=200),
                  confirm: str = Form(..., max_length=200)):
    if limited("reg" + ip(req), 8, 600):
        return page(req, "register.html", None, None, err="Too many tries. Wait a few minutes.")
    email = auth.norm_email(email)
    if not auth.valid_email(email):
        return page(req, "register.html", None, None, err="Enter a valid email.")
    if len(password) < 8:
        return page(req, "register.html", None, None, err="Password must be at least 8 characters.")
    if password != confirm:
        return page(req, "register.html", None, None, err="Passwords do not match.")
    sid = secrets.token_urlsafe(16)
    try:
        db.q("insert into u(sid,stage,goal,email,pw) values(?,?,?,?,?)",
             (sid, "planning", "A job", email, auth.hash_pw(password)))
    except sqlite3.IntegrityError:
        return page(req, "register.html", None, None, err="That email is already registered. Log in instead.")
    return go("/", sid)

@app.get("/login")
def login_get(req: Request):
    sid, u = current(req)
    if u: return go("/", sid)
    return page(req, "login.html", None, None, err=None)

@app.post("/login")
def login_post(req: Request, email: str = Form(..., max_length=200), password: str = Form(..., max_length=200)):
    if limited("login" + ip(req), 10, 600):
        return page(req, "login.html", None, None, err="Too many tries. Wait a few minutes.")
    email = auth.norm_email(email)
    rows = db.q("select * from u where email=?", (email,)) if email else []
    u = rows[0] if rows else None
    if not u or not u.get("pw") or not auth.check_pw(password, u["pw"]):
        return page(req, "login.html", None, None, err="Email or password is wrong.")
    return go("/", u["sid"])

@app.post("/logout")
def logout():
    r = RedirectResponse("/", 303); r.delete_cookie("sid"); return r

@app.get("/")
def home(req: Request):
    sid, u = current(req)
    if not u: return page(req, "index.html", None, None, stages=STAGES, cards=[])
    cards = [CARDS[k] for k in ORDER.get(u["stage"], ORDER["planning"])]
    return page(req, "index.html", sid, u, stages=STAGES, cards=cards)

@app.post("/stage")
def stage(req: Request, stage: str = Form(...), goal: str = Form(..., max_length=40)):
    sid, u, r = need(req)
    if r: return r
    if stage in STAGES: db.q("update u set stage=?, goal=? where sid=?", (stage, goal, sid))
    return go("/", sid)

@app.post("/demo")
def demo(req: Request):
    sid, u, r = need(req)
    if r: return r
    p = {"summary": "Product manager with 6 years in fintech, leading roadmaps and cross-functional teams.",
         "brk": "Planned maternity leave, using the time to mentor and upskill.",
         "skills": ["Product roadmapping", "Stakeholder management", "Mentoring", "Data analysis"]}
    db.q("update u set stage='expecting', goal='A job', profile=? where sid=?", (json.dumps(p), sid))
    db.q("delete from j where sid=?", (sid,))
    for l in ["Mentored two junior product managers through their first launches.", "Completed an online course in data analysis."]:
        db.q("insert into j(sid,raw,line) values(?,?,?)", (sid, l, l))
    return go("/", sid)

@app.post("/delete")
def delete(req: Request):
    sid, u, r = need(req)
    if r: return r
    for t in ("u", "j", "pg"): db.q(f"delete from {t} where sid=?", (sid,))
    r = RedirectResponse("/", 303); r.delete_cookie("sid"); return r

@app.get("/journal")
def journal(req: Request):
    sid, u, r = need(req)
    if r: return r
    return page(req, "journal.html", sid, u, entries=db.q("select raw,line from j where sid=? order by id desc", (sid,)))

@app.post("/journal")
def journal_add(req: Request, raw: str = Form(..., max_length=500)):
    sid, u, r = need(req)
    if r: return r
    d = ai.ask(f'Rewrite as one resume-ready line using only these facts. JSON {{"line": str}}.\n<data>{raw}</data>',
               {"line": raw}, model=ai.FAST, max_tokens=200, keys=("line",), allow=allow(sid))
    db.q("insert into j(sid,raw,line) values(?,?,?)", (sid, raw, str(d["line"])[:300]))
    return go("/journal", sid)

@app.get("/profile")
def profile(req: Request):
    sid, u, r = need(req)
    if r: return r
    return page(req, "profile.html", sid, u, draft=None)

@app.post("/profile")
def profile_gen(req: Request, text: str = Form(..., max_length=6000)):
    sid, u, r = need(req)
    if r: return r
    prompt = (f'Goal: {u["goal"]}. Return JSON {{"summary": str, "break_statement": str, "skills": [{{"name": str, "evidence": str}}]}}. '
              f'Every skill needs evidence taken from the text or journal below.\n<data>{text}</data>\nJournal:\n<data>{lines(sid)}</data>')
    fb = {"summary": text[:200], "break_statement": "Career break, now returning.",
          "skills": [{"name": "Communication", "evidence": "your description (demo response: no API key set)"}]}
    d = ai.ask(prompt, fb, keys=("summary", "break_statement", "skills"), allow=allow(sid))
    d["skills"] = [s for s in d["skills"] if isinstance(s, dict) and "name" in s][:12]
    return page(req, "profile.html", sid, u, draft=d)

@app.post("/profile/save")
def profile_save(req: Request, summary: str = Form(..., max_length=600), brk: str = Form("", max_length=300),
                 skills: List[str] = Form([])):
    sid, u, r = need(req)
    if r: return r
    db.q("update u set profile=? where sid=?", (json.dumps({"summary": summary, "brk": brk, "skills": [s[:60] for s in skills[:20]]}), sid))
    return go("/profile", sid)

@app.get("/jobs")
def jobs(req: Request):
    sid, u, r = need(req)
    if r: return r
    return page(req, "jobs.html", sid, u, jobs=load("jobs.json"), scores={}, paste=None)

@app.post("/jobs/match")
def jobs_match(req: Request):
    sid, u, r = need(req)
    if r: return r
    js = load("jobs.json"); sk = (u["prof"] or {}).get("skills", [])
    low = {s.lower() for s in sk}
    fb = {"matches": [{"id": j["id"], "score": min(95, 40 + 25 * len(low & set(j["tags"]))), "why": "Keyword overlap (demo response)."} for j in js]}
    d = ai.ask(f'Profile skills: {sk}. Score each job 0-100 for fit with a one-sentence reason, noting gap-friendly signals. '
               f'JSON {{"matches": [{{"id": int, "score": int, "why": str}}]}}. Jobs: {json.dumps(js)}', fb, keys=("matches",), allow=allow(sid))
    scores = {m["id"]: m for m in d["matches"] if isinstance(m, dict) and "id" in m}
    return page(req, "jobs.html", sid, u, jobs=js, scores=scores, paste=None)

@app.post("/jobs/paste")
def jobs_paste(req: Request, jd: str = Form(..., max_length=6000)):
    sid, u, r = need(req)
    if r: return r
    sk = (u["prof"] or {}).get("skills", [])
    fb = {"score": 0, "why": "Set ANTHROPIC_API_KEY for AI scoring.", "talking_points": []}
    d = ai.ask(f'Skills: {sk}. Rate fit for the job in the data tags. JSON {{"score": int, "why": str, "talking_points": [str]}}\n<data>{jd}</data>',
               fb, keys=("score", "why", "talking_points"), allow=allow(sid))
    return page(req, "jobs.html", sid, u, jobs=load("jobs.json"), scores={}, paste=d)

@app.get("/site")
def site(req: Request):
    sid, u, r = need(req)
    if r: return r
    return page(req, "site.html", sid, u, draft=None, pub=db.q("select slug from pg where sid=? and live=1", (sid,)), err=req.query_params.get("err"))

@app.post("/site/preview")
def site_preview(req: Request):
    sid, u, r = need(req)
    if r: return r
    if not u["prof"]: return go("/profile", sid)
    p = u["prof"]; fb = {"headline": "Hello, I'm back.", "about": p["summary"], "services": p["skills"][:4]}
    d = ai.ask(f'Write portfolio website copy using only this profile: {json.dumps(p)}. JSON {{"headline": str, "about": str, "services": [str]}}',
               fb, keys=("headline", "about", "services"), allow=allow(sid))
    c = {"headline": str(d["headline"])[:120], "about": str(d["about"])[:800], "services": [str(s)[:80] for s in d["services"][:5]]}
    return page(req, "site.html", sid, u, draft=c, draft_json=json.dumps(c), pub=[], err=None)

@app.post("/site/publish")
def site_publish(req: Request, slug: str = Form(...), content: str = Form(..., max_length=4000), confirm: str = Form("")):
    sid, u, r = need(req)
    if r: return r
    try:
        c = json.loads(content); c = {"headline": str(c["headline"])[:120], "about": str(c["about"])[:800], "services": [str(s)[:80] for s in c["services"][:5]]}
    except Exception: return go("/site?err=bad", sid)
    if confirm != "yes" or not re.fullmatch(r"[a-z0-9-]{3,30}", slug): return go("/site?err=bad", sid)
    own = db.q("select sid from pg where slug=?", (slug,))
    if own and own[0]["sid"] != sid: return go("/site?err=taken", sid)
    db.q("insert or replace into pg(slug,sid,content,live) values(?,?,?,1)", (slug, sid, json.dumps(c)))
    return go("/site", sid)

@app.post("/site/unpublish")
def site_unpublish(req: Request):
    sid, u, r = need(req)
    if r: return r
    db.q("update pg set live=0 where sid=?", (sid,)); return go("/site", sid)

@app.get("/p/{slug}")
def portfolio(req: Request, slug: str):
    sid, u = current(req)
    rec = db.q("select content from pg where slug=? and live=1", (slug,))
    if not rec: return HTMLResponse("Page not found", 404)
    return page(req, "portfolio.html", sid, u, c=json.loads(rec[0]["content"]))

@app.get("/money")
def money(req: Request):
    sid, u = current(req)
    return page(req, "money.html", sid, u, cards=load("finance.json"))

@app.get("/community")
def community(req: Request):
    sid, u, r = need(req)
    if r: return r
    return page(req, "community.html", sid, u)

def send_mail(name, email, msg):
    clean = lambda s: re.sub(r"[\r\n]+", " ", s)
    m = EmailMessage(); user = os.getenv("SMTP_USER"); pw = os.getenv("SMTP_PASS")
    m["Subject"] = "Comeback contact: " + clean(name)[:50]; m["From"] = user or "noreply@localhost"
    m["To"] = os.getenv("MAIL_TO") or user or "localhost"; m["Reply-To"] = clean(email)
    m.set_content(f"From: {clean(name)} <{clean(email)}>\n\n{msg}")
    if not (user and pw):
        os.makedirs("db", exist_ok=True); open("db/outbox.txt", "a").write(str(m) + "\n---\n"); return
    port = int(os.getenv("SMTP_PORT", "465")); host = os.getenv("SMTP_HOST", "smtpout.secureserver.net")
    with (smtplib.SMTP_SSL(host, port, timeout=15) if port == 465 else smtplib.SMTP(host, port, timeout=15)) as s:
        if port != 465: s.starttls()
        s.login(user, pw); s.send_message(m)

@app.get("/contact")
def contact(req: Request):
    sid, u = current(req)
    return page(req, "contact.html", sid, u, sent=req.query_params.get("sent"))

@app.post("/contact")
def contact_send(req: Request, name: str = Form(..., max_length=100), email: str = Form(..., max_length=200),
                 message: str = Form(..., max_length=3000), website: str = Form("")):
    sid, u = current(req)
    if not website and not limited(ip(req)) and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        try: send_mail(name, email, message)
        except Exception as e: print("Mail error:", e)
    return go("/contact?sent=1", sid)
