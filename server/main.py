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


def check_secret(given: Optional[str], expected: str, name: str):
    if not expected:
        raise HTTPException(status_code=500, detail=f"{name} not configured")
    if given != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


def gen_code() -> str:
    a = secrets.token_hex(2).upper()
    b = secrets.token_hex(2).upper()
    return f"V7-{a}-{b}"


@app.post("/issue")
def issue(req: IssueReq, x_bot_secret: Optional[str] = Header(None)):
    check_secret(x_bot_secret, BOT_SECRET, "BOT_SECRET")
    code = gen_code()
    expires_at = int(time.time()) + CODE_TTL_SECONDS
    with db() as conn:
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
