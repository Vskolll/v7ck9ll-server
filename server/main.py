import os
import sqlite3
import secrets
import time
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

BOT_SECRET = os.getenv("BOT_SECRET", "")
APP_SECRET = os.getenv("APP_SECRET", "")
DB_PATH = os.getenv("DB_PATH", "codes.db")
CODE_TTL_SECONDS = int(os.getenv("CODE_TTL_SECONDS", "600"))
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "600"))
SUBSCRIPTION_MONTH_SECONDS = int(os.getenv("SUBSCRIPTION_MONTH_SECONDS", str(30 * 24 * 60 * 60)))

app = FastAPI(title="V7CK9LL Code Server")


def db():
    return sqlite3.connect(DB_PATH)


def init_db():
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS codes (
                code TEXT PRIMARY KEY,
                user_id TEXT,
                expires_at INTEGER,
                used INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id TEXT PRIMARY KEY,
                expires_at INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                plan_months INTEGER,
                method TEXT,
                screenshot_file_id TEXT,
                status TEXT,
                created_at INTEGER,
                reviewed_at INTEGER,
                reviewer_id TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                device_id TEXT,
                expires_at INTEGER
            )
            """
        )


@app.on_event("startup")
def _startup():
    init_db()


class IssueReq(BaseModel):
    user_id: Optional[str] = None


class VerifyReq(BaseModel):
    code: str
    device_id: str


class ValidateReq(BaseModel):
    session_token: str


class PaymentCreateReq(BaseModel):
    user_id: str
    plan_months: int
    method: str


class PaymentAttachReq(BaseModel):
    payment_id: int
    screenshot_file_id: str


class PaymentReviewReq(BaseModel):
    payment_id: int
    reviewer_id: Optional[str] = None


class PaymentGetReq(BaseModel):
    payment_id: int


class PaymentListReq(BaseModel):
    status: Optional[str] = None
    limit: int = 20


class PaymentByUserReq(BaseModel):
    user_id: str
    limit: int = 20


class SubStatusReq(BaseModel):
    user_id: str


class SubExpiringReq(BaseModel):
    days: int = 3


def check_secret(given: Optional[str], expected: str, name: str):
    if not expected:
        raise HTTPException(status_code=500, detail=f"{name} not configured")
    if given != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


def gen_code() -> str:
    a = secrets.token_hex(2).upper()
    b = secrets.token_hex(2).upper()
    return f"V7-{a}-{b}"


def get_active_subscription(conn: sqlite3.Connection, user_id: str) -> Optional[int]:
    now = int(time.time())
    row = conn.execute(
        "SELECT expires_at FROM subscriptions WHERE user_id=?",
        (user_id,),
    ).fetchone()
    if not row:
        return None
    (expires_at,) = row
    if expires_at < now:
        return None
    return expires_at


def extend_subscription(conn: sqlite3.Connection, user_id: str, months: int) -> int:
    now = int(time.time())
    row = conn.execute(
        "SELECT expires_at FROM subscriptions WHERE user_id=?",
        (user_id,),
    ).fetchone()
    base = now
    if row:
        (current_expires,) = row
        if current_expires > now:
            base = current_expires
    new_expires = base + (months * SUBSCRIPTION_MONTH_SECONDS)
    conn.execute(
        "INSERT INTO subscriptions(user_id, expires_at) VALUES(?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET expires_at=excluded.expires_at",
        (user_id, new_expires),
    )
    return new_expires


@app.post("/issue")
def issue(req: IssueReq, x_bot_secret: Optional[str] = Header(None)):
    check_secret(x_bot_secret, BOT_SECRET, "BOT_SECRET")
    if not req.user_id:
        raise HTTPException(status_code=400, detail="user_id_required")
    code = gen_code()
    expires_at = int(time.time()) + CODE_TTL_SECONDS
    with db() as conn:
        active = get_active_subscription(conn, req.user_id)
        if not active:
            raise HTTPException(status_code=403, detail="subscription_required")
        conn.execute(
            "INSERT INTO codes(code, user_id, expires_at, used) VALUES(?, ?, ?, 0)",
            (code, req.user_id or "", expires_at),
        )
    return {"code": code, "expires_at": expires_at}


@app.post("/verify")
def verify(req: VerifyReq, x_app_secret: Optional[str] = Header(None)):
    check_secret(x_app_secret, APP_SECRET, "APP_SECRET")
    now = int(time.time())
    with db() as conn:
        row = conn.execute(
            "SELECT code, expires_at, used FROM codes WHERE code=?",
            (req.code,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="invalid_code")
        code, expires_at, used = row
        if used:
            raise HTTPException(status_code=400, detail="code_used")
        if expires_at < now:
            raise HTTPException(status_code=400, detail="code_expired")
        conn.execute("UPDATE codes SET used=1 WHERE code=?", (code,))

        token = secrets.token_urlsafe(32)
        session_expires = now + SESSION_TTL_SECONDS
        conn.execute(
            "INSERT INTO sessions(token, device_id, expires_at) VALUES(?, ?, ?)",
            (token, req.device_id, session_expires),
        )
    return {"ok": True, "session_token": token, "expires_at": session_expires}


@app.post("/validate")
def validate(req: ValidateReq, x_app_secret: Optional[str] = Header(None)):
    check_secret(x_app_secret, APP_SECRET, "APP_SECRET")
    now = int(time.time())
    with db() as conn:
        row = conn.execute(
            "SELECT token, expires_at FROM sessions WHERE token=?",
            (req.session_token,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="invalid_session")
        _, expires_at = row
        if expires_at < now:
            raise HTTPException(status_code=400, detail="session_expired")
    return {"ok": True, "expires_at": expires_at}


@app.post("/payment/create")
def payment_create(req: PaymentCreateReq, x_bot_secret: Optional[str] = Header(None)):
    check_secret(x_bot_secret, BOT_SECRET, "BOT_SECRET")
    now = int(time.time())
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO payments(user_id, plan_months, method, status, created_at)"
            " VALUES(?, ?, ?, 'pending', ?)",
            (req.user_id, req.plan_months, req.method, now),
        )
        payment_id = cur.lastrowid
    return {"payment_id": payment_id}


@app.post("/payment/attach")
def payment_attach(req: PaymentAttachReq, x_bot_secret: Optional[str] = Header(None)):
    check_secret(x_bot_secret, BOT_SECRET, "BOT_SECRET")
    with db() as conn:
        row = conn.execute(
            "SELECT status FROM payments WHERE id=?",
            (req.payment_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="payment_not_found")
        (status,) = row
        if status != "pending":
            raise HTTPException(status_code=400, detail="payment_not_pending")
        conn.execute(
            "UPDATE payments SET screenshot_file_id=? WHERE id=?",
            (req.screenshot_file_id, req.payment_id),
        )
    return {"ok": True}


@app.post("/payment/approve")
def payment_approve(req: PaymentReviewReq, x_bot_secret: Optional[str] = Header(None)):
    check_secret(x_bot_secret, BOT_SECRET, "BOT_SECRET")
    now = int(time.time())
    with db() as conn:
        row = conn.execute(
            "SELECT user_id, plan_months, status FROM payments WHERE id=?",
            (req.payment_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="payment_not_found")
        user_id, plan_months, status = row
        if status != "pending":
            raise HTTPException(status_code=400, detail="payment_not_pending")
        conn.execute(
            "UPDATE payments SET status='approved', reviewed_at=?, reviewer_id=? WHERE id=?",
            (now, req.reviewer_id or "", req.payment_id),
        )
        new_expires = extend_subscription(conn, user_id, int(plan_months))
    return {"ok": True, "user_id": user_id, "expires_at": new_expires}


@app.post("/payment/reject")
def payment_reject(req: PaymentReviewReq, x_bot_secret: Optional[str] = Header(None)):
    check_secret(x_bot_secret, BOT_SECRET, "BOT_SECRET")
    now = int(time.time())
    with db() as conn:
        row = conn.execute(
            "SELECT user_id, status FROM payments WHERE id=?",
            (req.payment_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="payment_not_found")
        user_id, status = row
        if status != "pending":
            raise HTTPException(status_code=400, detail="payment_not_pending")
        conn.execute(
            "UPDATE payments SET status='rejected', reviewed_at=?, reviewer_id=? WHERE id=?",
            (now, req.reviewer_id or "", req.payment_id),
        )
    return {"ok": True, "user_id": user_id}


@app.post("/sub/status")
def sub_status(req: SubStatusReq, x_bot_secret: Optional[str] = Header(None)):
    check_secret(x_bot_secret, BOT_SECRET, "BOT_SECRET")
    with db() as conn:
        active_expires = get_active_subscription(conn, req.user_id)
    if not active_expires:
        return {"active": False, "expires_at": None}
    return {"active": True, "expires_at": active_expires}


@app.post("/sub/expiring")
def sub_expiring(req: SubExpiringReq, x_bot_secret: Optional[str] = Header(None)):
    check_secret(x_bot_secret, BOT_SECRET, "BOT_SECRET")
    now = int(time.time())
    until = now + (req.days * 24 * 60 * 60)
    with db() as conn:
        rows = conn.execute(
            "SELECT user_id, expires_at FROM subscriptions WHERE expires_at <= ?",
            (until,),
        ).fetchall()
    return {"items": [{"user_id": r[0], "expires_at": r[1]} for r in rows]}


@app.post("/payment/get")
def payment_get(req: PaymentGetReq, x_bot_secret: Optional[str] = Header(None)):
    check_secret(x_bot_secret, BOT_SECRET, "BOT_SECRET")
    with db() as conn:
        row = conn.execute(
            "SELECT id, user_id, plan_months, method, screenshot_file_id, status, created_at, reviewed_at, reviewer_id "
            "FROM payments WHERE id=?",
            (req.payment_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="payment_not_found")
    return {
        "payment": {
            "id": row[0],
            "user_id": row[1],
            "plan_months": row[2],
            "method": row[3],
            "screenshot_file_id": row[4],
            "status": row[5],
            "created_at": row[6],
            "reviewed_at": row[7],
            "reviewer_id": row[8],
        }
    }


@app.post("/payment/list")
def payment_list(req: PaymentListReq, x_bot_secret: Optional[str] = Header(None)):
    check_secret(x_bot_secret, BOT_SECRET, "BOT_SECRET")
    limit = max(1, min(int(req.limit), 100))
    with db() as conn:
        if req.status:
            rows = conn.execute(
                "SELECT id, user_id, plan_months, method, status, created_at "
                "FROM payments WHERE status=? ORDER BY id DESC LIMIT ?",
                (req.status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, user_id, plan_months, method, status, created_at "
                "FROM payments ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    items = []
    for r in rows:
        items.append(
            {
                "id": r[0],
                "user_id": r[1],
                "plan_months": r[2],
                "method": r[3],
                "status": r[4],
                "created_at": r[5],
            }
        )
    return {"items": items}


@app.post("/payment/by_user")
def payment_by_user(req: PaymentByUserReq, x_bot_secret: Optional[str] = Header(None)):
    check_secret(x_bot_secret, BOT_SECRET, "BOT_SECRET")
    limit = max(1, min(int(req.limit), 100))
    with db() as conn:
        rows = conn.execute(
            "SELECT id, user_id, plan_months, method, status, created_at "
            "FROM payments WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (req.user_id, limit),
        ).fetchall()
    items = []
    for r in rows:
        items.append(
            {
                "id": r[0],
                "user_id": r[1],
                "plan_months": r[2],
                "method": r[3],
                "status": r[4],
                "created_at": r[5],
            }
        )
    return {"items": items}
