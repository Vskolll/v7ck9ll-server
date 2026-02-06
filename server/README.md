# V7CK9LL Server (FastAPI)

## Env (Render)
```
BOT_SECRET=change_me
APP_SECRET=change_me
DB_PATH=/data/codes.db
CODE_TTL_SECONDS=600
SESSION_TTL_SECONDS=600
```

## Run locally
```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Endpoints
- POST /issue (bot)
  - Header: X-Bot-Secret
  - Body: { "user_id": "123" }
- POST /verify (app)
  - Header: X-App-Secret
  - Body: { "code": "V7-XXXX-XXXX", "device_id": "android-id" }
- POST /validate (optional)
  - Header: X-App-Secret
  - Body: { "session_token": "..." }
