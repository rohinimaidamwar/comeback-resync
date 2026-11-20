import os
import sqlite3

P = os.getenv("DB_PATH", "db/app.db")


def db():
    c = sqlite3.connect(P)
    c.row_factory = sqlite3.Row
    return c


def q(sql, a=()):
    c = db()
    cur = c.execute(sql, a)
    rows = [dict(r) for r in cur.fetchall()]
    c.commit()
    c.close()
    return rows


def init():
    os.makedirs(os.path.dirname(P), exist_ok=True)
    c = db()
    c.executescript("""create table if not exists u(sid text primary key, stage text, goal text, profile text);
create table if not exists j(id integer primary key, sid text, raw text, line text);
create table if not exists pg(slug text primary key, sid text, content text, live int);""")
    cols = {r[1] for r in c.execute("pragma table_info(u)")}
    if "email" not in cols:
        c.execute("alter table u add column email text")
    if "pw" not in cols:
        c.execute("alter table u add column pw text")
    if "name" not in cols:
        c.execute("alter table u add column name text")
    jcols = {r[1] for r in c.execute("pragma table_info(j)")}
    if "tags" not in jcols:
        c.execute("alter table j add column tags text")  # JSON list of skill tags
    c.execute(
        "create unique index if not exists u_email on u(email) where email is not null and email != ''"
    )
    c.commit()
    c.close()
