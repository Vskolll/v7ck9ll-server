# V7CK9LL Server (FastAPI)

## Env (Render)
```
BOT_SECRET=change_me
APP_SECRET=change_me
DB_PATH=/data/codes.db
CODE_TTL_SECONDS=600
SESSION_TTL_SECONDS=600
SUBSCRIPTION_MONTH_SECONDS=2592000
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
- POST /payment/create (bot)
  - Header: X-Bot-Secret
  - Body: { "user_id": "123", "plan_months": 3, "method": "UA" }
- POST /payment/attach (bot)
  - Header: X-Bot-Secret
  - Body: { "payment_id": 1, "screenshot_file_id": "file_id" }
- POST /payment/approve (bot)
  - Header: X-Bot-Secret
  - Body: { "payment_id": 1, "reviewer_id": "999" }
- POST /payment/reject (bot)
  - Header: X-Bot-Secret
  - Body: { "payment_id": 1, "reviewer_id": "999" }
- POST /payment/get (bot)
  - Header: X-Bot-Secret
  - Body: { "payment_id": 1 }
- POST /payment/list (bot)
  - Header: X-Bot-Secret
  - Body: { "status": "pending", "limit": 20 }
- POST /payment/by_user (bot)
  - Header: X-Bot-Secret
  - Body: { "user_id": "123", "limit": 20 }
- POST /sub/status (bot)
  - Header: X-Bot-Secret
  - Body: { "user_id": "123" }
- POST /sub/expiring (bot)
  - Header: X-Bot-Secret
  - Body: { "days": 3 }
- POST /verify (app)
  - Header: X-App-Secret
  - Body: { "code": "V7-XXXX-XXXX", "device_id": "android-id" }
- POST /validate (optional)
  - Header: X-App-Secret
  - Body: { "session_token": "..." }
