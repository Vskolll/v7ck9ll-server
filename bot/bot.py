import os
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
SERVER_URL = os.getenv("SERVER_URL", "")
BOT_SECRET = os.getenv("BOT_SECRET", "")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Нажми /key чтобы получить одноразовый код (10 минут).")


async def key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SERVER_URL or not BOT_SECRET:
        await update.message.reply_text("Сервер не настроен.")
        return
    try:
        r = requests.post(
            f"{SERVER_URL}/issue",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"user_id": str(update.effective_user.id)}
        )
        if r.status_code != 200:
            await update.message.reply_text("Ошибка сервера при выдаче кода.")
            return
        data = r.json()
        code = data.get("code", "")
        await update.message.reply_text(f"Твой код: {code}\nДействует 10 минут.")
    except Exception:
        await update.message.reply_text("Ошибка сети.")


def main():
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("key", key))
    app.run_polling()


if __name__ == "__main__":
    main()
