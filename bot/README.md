# Telegram Bot

## Env
```
TELEGRAM_BOT_TOKEN=...
SERVER_URL=https://your-service.onrender.com
BOT_SECRET=...
ADMIN_IDS=123,456
PAY_UA=...
PAY_RU=...
PAY_CRYPTO=...
PLAN_PRICES=1:80,3:210,6:360,12:600
```

## Run locally
```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

## Usage
- /start
- /buy (покупка подписки)
- /status (статус подписки)
- /key (выдаёт одноразовый код на 10 минут)
- /approve <payment_id> (админ)
- /reject <payment_id> (админ)
