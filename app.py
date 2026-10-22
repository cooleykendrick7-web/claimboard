"""
ClaimBoard — Ken's live claims dashboard.
Real database-backed site: claim statuses, totals and the money counter are
computed from SQLite on every request (no static numbers). Ken confirms which
found claims genuinely apply to him (owner login); the daily Claim Finder
sweep and Milli's filing work update statuses through an admin API keyed by
the same owner password. No personal identifiers (SSN etc.) are ever stored
here — amounts, names of claims, deadlines and statuses only.
"""
import os, json, time, hmac, hashlib, secrets, sqlite3, datetime
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE = Path(__file__).parent
DB_PATH = os.environ.get("CLAIMBOARD_DB", str(BASE / "claimboard.db"))
OWNER_PASSWORD = os.environ.get("CLAIMBOARD_OWNER_PASSWORD", "claims-owner-2026")
SESSION_SECRET = os.environ.get("CLAIMBOARD_SESSION_SECRET", secrets.token_hex(32))

app = FastAPI(title="ClaimBoard", version="1.2.0")

# Realistic payout estimate ranges (low, high) per claim — NOT the headline
# numbers. State claims are Ken's actual money (counted at face, with two
# honest adjustments: CA low excludes the disputed $72 Western Air item; TX low
# assumes the royalty co-owned with his aunt is split). Flat settlements count
# in full; published ranges count as printed; "up to $X" settlements count at a
# conservative slice because final payouts are split across all claimants.
# None = no published payout — excluded from dollar tallies, counted separately.
ESTIMATES = {
 "tx-unclaimed": (1272.07, 2219.79), "va-unclaimed": (1000.0, 1000.0),
 "ca-unclaimed": (563.01, 635.01), "ks-unclaimed": (277.04, 277.04),
 "pa-unclaimed": (53.85, 53.85), "ms-unclaimed": (50.0, 50.0),
 "il-unclaimed": (47.0, 47.0), "in-unclaimed": (31.17, 31.17),
 "ct-unclaimed": (13.0, 13.0), "co-unclaimed": (10.0, 10.0),
 "pork": None, "bestway": (40.0, 40.0), "connectoncall": (15.0, 75.0),
 "forbes": (32.0, 189.0), "cvs": (2.0, 5.0), "lsc": (25.0, 250.0),
 "venetian": (3.60, 71.0), "skin360": None, "squatch": (0.50, 2.50),
 "apple": (25.0, 25.0), "equifax": (95.0, 280.0), "goodrx": None, "atm": None,
}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

SEED = [
 # slug, name, kind, face_value (numeric or None), estimate_label, deadline, url, status, note
 ("tx-unclaimed","Texas unclaimed property","state",2219.79,"$2,219.79",None,"","filed","Docs next — royalty co-owned with aunt Joyce"),
 ("va-unclaimed","Virginia unclaimed property","state",1000.0,"$1,000+", "2027-01-01","","filed","Docs next — exact amount not shown by state"),
 ("ca-unclaimed","California unclaimed property","state",635.01,"$635.01","2026-11-17","","docs_submitting","Docs in portal; robot-check last step"),
 ("ks-unclaimed","Kansas unclaimed property","state",277.04,"$277.04",None,"","filed","Needs notary or original cashier's check"),
 ("pa-unclaimed","Pennsylvania unclaimed property","state",53.85,"$53.85",None,"","filed","Nothing needed — processing"),
 ("ms-unclaimed","Mississippi unclaimed property","state",50.0,"$50.00","2027-01-01","","filed","Needs notarized signature"),
 ("il-unclaimed","Illinois unclaimed property","state",47.0,"$47.00",None,"","filed","Docs next"),
 ("in-unclaimed","Indiana unclaimed property","state",31.17,"$31.17",None,"","filed","Docs next"),
 ("ct-unclaimed","Connecticut unclaimed property","state",13.0,"$13.00",None,"","filed","Docs next — ID front + back"),
 ("co-unclaimed","Colorado unclaimed property","state",10.0,"$10.00",None,"","filed","Docs next"),
 ("pork","Pork Price-Fixing settlement","settlement",None,"not published","2026-10-29","https://www.overchargedforpork.com","found","Bought pork/bacon 2014–2018 (ND counts, MS doesn't)"),
 ("bestway","Bestway Pools settlement","settlement",40.0,"$40 flat","2026-10-30","https://www.poolsettlementbw.com","found","Bought a 48in+ Bestway/Coleman pool 2008–2024"),
 ("connectoncall","ConnectOnCall data breach","settlement",75.0,"up to $75","2026-11-02","https://www.connectoncallsettlement.com","found","Called a doctor's office after hours 2014–2024"),
 ("forbes","Forbes tracking settlement (CA only)","settlement",None,"~$32–$189","2026-11-09","https://www.mediasitetrackersettlement.com","found","California residents only"),
 ("cvs","CVS digital privacy settlement","settlement",5.0,"up to $5","2026-11-16","https://www.cvsdigitalprivacysettlement.com","found","Used cvs.com or the CVS app before Jul 2026"),
 ("lsc","LSC lab data breach","settlement",None,"up to $1,000","2026-11-24","https://www.lscdatasettlement.com","found","Lab tests ordered by a Planned Parenthood center"),
 ("venetian","Venetian Las Vegas privacy (CA only)","settlement",None,"~$71 / ~$3.60","2026-11-24","https://www.venetianlasvegassettlement.com","found","California residents only"),
 ("skin360","Neutrogena Skin360 BIPA (IL only)","settlement",None,"not published","2026-11-25","https://www.skin360bipasettlement.com","found","Illinois only"),
 ("squatch","Dr. Squatch 'natural' labels","settlement",2.50,"up to $2.50 no-proof","2026-11-27","https://www.personalcareproductssettlement.com","found","Bought 'natural' Dr. Squatch 2018–2026"),
 ("apple","Apple Intelligence / Siri settlement","settlement",25.0,"$25 per phone","2026-12-21","https://www.smartphoneaisettlement.com","found","Bought iPhone 15 Pro or any 16, Jun 2024–Mar 2025"),
 ("equifax","Equifax credit score error","settlement",None,"$95–$280","2026-12-28","https://www.equifaxfaircreditreportingsettlement.com","found","Needs the Claim ID from Equifax's notice to you"),
 ("goodrx","GoodRx privacy settlement","settlement",None,"not published","2026-12-29","https://www.goodrxprivacysettlement.com","found","Used GoodRx before Apr 2024 — filing opens by Oct 30"),
 ("atm","Visa/MC non-bank ATM surcharge","settlement",None,"not published","2027-02-10","https://www.nonbankatmsurchargesettlement.com","found","Paid fees at independent ATMs 2007–2026"),
]

STATUSES = ("found","confirmed","filed","docs_submitting","paid","closed","not_mine")

def init_db():
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS claims(
      slug TEXT PRIMARY KEY, name TEXT, kind TEXT, face_value REAL,
      estimate_label TEXT, deadline TEXT, url TEXT, status TEXT, note TEXT,
      paid_amount REAL DEFAULT 0, updated_at TEXT)""")
    for row in SEED:
        c.execute("INSERT OR IGNORE INTO claims(slug,name,kind,face_value,estimate_label,deadline,url,status,note,updated_at)"
                  " VALUES(?,?,?,?,?,?,?,?,?,?)", (*row, datetime.datetime.utcnow().isoformat()))
    cols = {r[1] for r in c.execute("PRAGMA table_info(claims)")}
    for col in ("est_low", "est_high"):
        if col not in cols:
            c.execute(f"ALTER TABLE claims ADD COLUMN {col} REAL")
    for slug, est in ESTIMATES.items():
        if est is None:
            c.execute("UPDATE claims SET est_low=NULL, est_high=NULL WHERE slug=?", (slug,))
        else:
            c.execute("UPDATE claims SET est_low=?, est_high=? WHERE slug=?", (est[0], est[1], slug))
    c.commit(); c.close()
init_db()

def sign(val: str) -> str:
    sig = hmac.new(SESSION_SECRET.encode(), val.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{val}.{sig}"

def is_owner(request: Request) -> bool:
    tok = request.cookies.get("cb_owner")
    if not tok or "." not in tok: return False
    val, sig = tok.rsplit(".", 1)
    expect = hmac.new(SESSION_SECRET.encode(), val.encode(), hashlib.sha256).hexdigest()[:32]
    return val == "owner" and hmac.compare_digest(sig, expect)

def admin_ok(request: Request) -> bool:
    key = request.headers.get("x-admin-key", "")
    return hmac.compare_digest(key, OWNER_PASSWORD) or is_owner(request)

@app.middleware("http")
async def headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp

@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "claimboard", "version": "1.2.0"}

@app.get("/api/claims")
async def api_claims():
    c = db(); rows = c.execute("SELECT * FROM claims ORDER BY (deadline IS NULL), deadline, kind DESC, face_value DESC").fetchall(); c.close()
    return [dict(r) for r in rows]

@app.get("/api/summary")
async def api_summary():
    c = db(); rows = c.execute("SELECT * FROM claims").fetchall(); c.close()
    paid = sum((r["paid_amount"] or 0) for r in rows if r["status"] == "paid")
    pipeline = sum((r["face_value"] or 0) for r in rows if r["status"] in ("filed", "docs_submitting"))
    confirmed_value = sum((r["face_value"] or 0) for r in rows if r["status"] == "confirmed")
    inmotion = [r for r in rows if r["status"] in ("confirmed", "filed", "docs_submitting")]
    priced = [r for r in inmotion if r["est_low"] is not None]
    est_low = sum(r["est_low"] for r in priced); est_high = sum(r["est_high"] for r in priced)
    waiting = [r for r in rows if r["status"] == "found" and r["est_low"] is not None]
    return {
        "paid_total": round(paid, 2),
        "pipeline_total": round(pipeline, 2),
        "confirmed_total": round(confirmed_value, 2),
        "est_low_total": round(est_low, 2),
        "est_high_total": round(est_high, 2),
        "est_best_total": round((est_low + est_high) / 2, 2),
        "est_priced_count": len(priced),
        "est_unpriced_count": len(inmotion) - len(priced),
        "found_est_low": round(sum(r["est_low"] for r in waiting), 2),
        "found_est_high": round(sum(r["est_high"] for r in waiting), 2),
        "counts": {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES},
        "total_claims": len(rows),
        "updated": datetime.datetime.utcnow().isoformat(),
    }

class LoginIn(BaseModel):
    password: str

@app.post("/api/login")
async def api_login(body: LoginIn):
    if hmac.compare_digest(body.password or "", OWNER_PASSWORD):
        resp = JSONResponse({"ok": True})
        resp.set_cookie("cb_owner", sign("owner"), httponly=True, samesite="lax", max_age=60*60*24*30)
        return resp
    raise HTTPException(401, "Wrong owner password.")

@app.post("/api/logout")
async def api_logout():
    resp = JSONResponse({"ok": True}); resp.delete_cookie("cb_owner"); return resp

@app.get("/api/me")
async def api_me(request: Request):
    return {"owner": is_owner(request)}

class StatusIn(BaseModel):
    status: str

@app.patch("/api/claims/{slug}")
async def api_set_status(slug: str, body: StatusIn, request: Request):
    if not admin_ok(request):
        raise HTTPException(401, "Owner login required.")
    if body.status not in STATUSES:
        raise HTTPException(400, "Invalid status.")
    c = db()
    cur = c.execute("UPDATE claims SET status=?, updated_at=? WHERE slug=?",
                    (body.status, datetime.datetime.utcnow().isoformat(), slug))
    c.commit(); n = cur.rowcount; c.close()
    if not n: raise HTTPException(404, "Claim not found.")
    return {"ok": True, "slug": slug, "status": body.status}

class ClaimIn(BaseModel):
    slug: str; name: str; kind: str = "settlement"; face_value: float | None = None
    estimate_label: str = ""; deadline: str | None = None; url: str = ""
    status: str = "found"; note: str = ""
    est_low: float | None = None; est_high: float | None = None

@app.post("/api/admin/claims")
async def api_upsert(body: ClaimIn, request: Request):
    if not admin_ok(request):
        raise HTTPException(401, "Admin key required.")
    c = db()
    c.execute("INSERT INTO claims(slug,name,kind,face_value,estimate_label,deadline,url,status,note,est_low,est_high,updated_at)"
              " VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(slug) DO UPDATE SET name=excluded.name,"
              " estimate_label=excluded.estimate_label, deadline=excluded.deadline, url=excluded.url,"
              " note=excluded.note, est_low=COALESCE(excluded.est_low, claims.est_low),"
              " est_high=COALESCE(excluded.est_high, claims.est_high), updated_at=excluded.updated_at",
              (body.slug, body.name, body.kind, body.face_value, body.estimate_label, body.deadline,
               body.url, body.status, body.note, body.est_low, body.est_high,
               datetime.datetime.utcnow().isoformat()))
    c.commit(); c.close()
    return {"ok": True, "slug": body.slug}

class PaidIn(BaseModel):
    amount: float

@app.post("/api/admin/claims/{slug}/paid")
async def api_paid(slug: str, body: PaidIn, request: Request):
    if not admin_ok(request):
        raise HTTPException(401, "Admin key required.")
    c = db()
    c.execute("UPDATE claims SET status='paid', paid_amount=?, updated_at=? WHERE slug=?",
              (body.amount, datetime.datetime.utcnow().isoformat(), slug))
    c.commit(); c.close()
    return {"ok": True}

app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(str(BASE / "static" / "index.html"))

@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(str(BASE / "static" / "manifest.webmanifest"), media_type="application/manifest+json")

@app.get("/sw.js")
async def sw():
    return FileResponse(str(BASE / "static" / "sw.js"), media_type="application/javascript")
