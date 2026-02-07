import os
import time
from typing import Optional

import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
SERVER_URL = os.getenv("SERVER_URL", "")
BOT_SECRET = os.getenv("BOT_SECRET", "")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}

PAY_UA = os.getenv("PAY_UA", "")
PAY_RU = os.getenv("PAY_RU", "")
PAY_CRYPTO = os.getenv("PAY_CRYPTO", "")

PLAN_PRICES = os.getenv("PLAN_PRICES", "1:80,3:210,6:360,12:600")

PLAN_LABELS = {
    1: "1 месяц",
    3: "3 месяца",
    6: "6 месяцев",
    12: "1 год",
}

METHOD_LABELS = {
    "UA": "Украина",
    "RU": "Россия",
    "CRYPTO": "CRYPTO",
}


def parse_plan_prices(raw: str) -> dict[int, int]:
    out: dict[int, int] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            continue
        months_s, price_s = part.split(":", 1)
        try:
            months = int(months_s.strip())
            price = int(price_s.strip())
        except ValueError:
            continue
        out[months] = price
    return out


PLAN_PRICES_MAP = parse_plan_prices(PLAN_PRICES)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Доступ к кодам только по подписке.\n"
        "Команды:\n"
        "/buy — купить подписку\n"
        "/status — статус подписки\n"
        "/key — получить одноразовый код (10 минут)"
    )


def is_admin(user_id: Optional[int]) -> bool:
    return user_id in ADMIN_IDS


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
        if r.status_code == 403:
            await update.message.reply_text("Подписка не активна. Используй /buy.")
            return
        if r.status_code != 200:
            await update.message.reply_text("Ошибка сервера при выдаче кода.")
            return
        data = r.json()
        code = data.get("code", "")
        await update.message.reply_text(f"Android код: {code}\nДействует 10 минут.")
    except Exception:
        await update.message.reply_text("Ошибка сети.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SERVER_URL or not BOT_SECRET:
        await update.message.reply_text("Сервер не настроен.")
        return
    try:
        r = requests.post(
            f"{SERVER_URL}/sub/status",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"user_id": str(update.effective_user.id)}
        )
        if r.status_code != 200:
            await update.message.reply_text("Ошибка сервера при проверке подписки.")
            return
        data = r.json()
        if not data.get("active"):
            await update.message.reply_text("Подписка не активна. Используй /buy.")
            return
        expires_at = int(data.get("expires_at", 0))
        days_left = max(0, int((expires_at - int(time.time())) / 86400))
        await update.message.reply_text(
            f"Подписка активна до {time.strftime('%Y-%m-%d', time.localtime(expires_at))} "
            f"(осталось {days_left} дн.)."
        )
        if days_left <= 3:
            await update.message.reply_text("Подписка скоро закончится. Продли через /buy.")
    except Exception:
        await update.message.reply_text("Ошибка сети.")


async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prices = PLAN_PRICES_MAP
    lines = ["Выбери срок подписки (ответь числом):"]
    for months in (1, 3, 6, 12):
        label = PLAN_LABELS.get(months, f"{months} мес.")
        price = prices.get(months)
        price_text = f"${price}" if price is not None else "уточнить цену"
        lines.append(f"{months} — {label} — {price_text}")
    await update.message.reply_text("\n".join(lines))
    context.user_data["stage"] = "plan"


def method_instructions(method: str) -> str:
    if method == "UA" and PAY_UA:
        return f"Реквизиты Украина:\n{PAY_UA}"
    if method == "RU" and PAY_RU:
        return f"Реквизиты Россия:\n{PAY_RU}"
    if method == "CRYPTO" and PAY_CRYPTO:
        return f"Реквизиты CRYPTO:\n{PAY_CRYPTO}"
    return "Реквизиты пока не настроены."


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    text = (update.message.text or "").strip().upper()
    stage = context.user_data.get("stage")

    if stage == "plan":
        try:
            months = int(text)
        except ValueError:
            await update.message.reply_text("Нужно число 1, 3, 6 или 12.")
            return
        if months not in (1, 3, 6, 12):
            await update.message.reply_text("Нужно число 1, 3, 6 или 12.")
            return
        context.user_data["plan_months"] = months
        context.user_data["stage"] = "method"
        await update.message.reply_text("Выбери способ оплаты: UA / RU / CRYPTO")
        return

    if stage == "method":
        method = text
        if method not in ("UA", "RU", "CRYPTO"):
            await update.message.reply_text("Нужно выбрать: UA / RU / CRYPTO")
            return
        months = context.user_data.get("plan_months")
        if not months:
            context.user_data.pop("stage", None)
            await update.message.reply_text("Срок не выбран. Начни заново /buy.")
            return
        try:
            r = requests.post(
                f"{SERVER_URL}/payment/create",
                headers={"X-Bot-Secret": BOT_SECRET},
                json={
                    "user_id": str(update.effective_user.id),
                    "plan_months": int(months),
                    "method": method,
                },
            )
            if r.status_code != 200:
                await update.message.reply_text("Ошибка сервера при создании платежа.")
                return
            payment_id = r.json().get("payment_id")
        except Exception:
            await update.message.reply_text("Ошибка сети.")
            return

        context.user_data["payment_id"] = payment_id
        context.user_data["method"] = method
        context.user_data["stage"] = "screenshot"
        await update.message.reply_text(
            f"{method_instructions(method)}\n\n"
            "После оплаты пришли скрин платежа одним фото."
        )
        return


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.photo:
        return
    stage = context.user_data.get("stage")
    if stage != "screenshot":
        return
    payment_id = context.user_data.get("payment_id")
    method = context.user_data.get("method")
    months = context.user_data.get("plan_months")
    if not payment_id:
        await update.message.reply_text("Платеж не найден. Начни заново /buy.")
        context.user_data.pop("stage", None)
        return
    file_id = update.message.photo[-1].file_id
    try:
        r = requests.post(
            f"{SERVER_URL}/payment/attach",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"payment_id": int(payment_id), "screenshot_file_id": file_id},
        )
        if r.status_code != 200:
            await update.message.reply_text("Ошибка сервера при сохранении скрина.")
            return
    except Exception:
        await update.message.reply_text("Ошибка сети.")
        return

    for admin_id in ADMIN_IDS:
        await context.bot.send_photo(
            chat_id=admin_id,
            photo=file_id,
            caption=(
                "Новый платеж на проверку:\n"
                f"payment_id: {payment_id}\n"
                f"user_id: {update.effective_user.id}\n"
                f"plan: {months} мес\n"
                f"method: {method}\n"
                "Команды: /approve <id> или /reject <id>"
            ),
        )

    await update.message.reply_text("Скрин отправлен админу. Ожидай подтверждения.")
    context.user_data.pop("stage", None)


async def remind_expiring(context: ContextTypes.DEFAULT_TYPE, days: int, label: str):
    if not SERVER_URL or not BOT_SECRET:
        return
    key_name = f"reminded_expiring_{days}"
    reminded = context.application.bot_data.setdefault(key_name, set())
    try:
        r = requests.post(
            f"{SERVER_URL}/sub/expiring",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"days": days},
        )
        if r.status_code != 200:
            return
        items = r.json().get("items", [])
    except Exception:
        return

    for item in items:
        user_id = item.get("user_id")
        expires_at = int(item.get("expires_at", 0))
        if not user_id or not expires_at:
            continue
        key = f"{user_id}:{expires_at}"
        if key in reminded:
            continue
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text=(
                    f"{label}\n"
                    f"Дата окончания: {time.strftime('%Y-%m-%d', time.localtime(expires_at))}\n"
                    "Продли подписку через /buy."
                ),
            )
            reminded.add(key)
        except Exception:
            continue


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Недостаточно прав.")
        return
    if not context.args:
        await update.message.reply_text("Используй: /approve <payment_id>")
        return
    try:
        payment_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("payment_id должен быть числом.")
        return
    try:
        r = requests.post(
            f"{SERVER_URL}/payment/approve",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"payment_id": payment_id, "reviewer_id": str(update.effective_user.id)},
        )
        if r.status_code != 200:
            await update.message.reply_text("Ошибка сервера при подтверждении.")
            return
        data = r.json()
        user_id = int(data.get("user_id"))
        expires_at = int(data.get("expires_at", 0))
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "Платеж подтвержден. Подписка активна до "
                f"{time.strftime('%Y-%m-%d', time.localtime(expires_at))}.\n"
                "Можешь получить код: /key"
            ),
        )
        await update.message.reply_text("Готово. Подписка активирована.")
    except Exception:
        await update.message.reply_text("Ошибка сети.")


async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Недостаточно прав.")
        return
    if not context.args:
        await update.message.reply_text("Используй: /reject <payment_id>")
        return
    try:
        payment_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("payment_id должен быть числом.")
        return
    try:
        r = requests.post(
            f"{SERVER_URL}/payment/reject",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"payment_id": payment_id, "reviewer_id": str(update.effective_user.id)},
        )
        if r.status_code != 200:
            await update.message.reply_text("Ошибка сервера при отклонении.")
            return
        data = r.json()
        user_id = int(data.get("user_id"))
        await context.bot.send_message(
            chat_id=user_id,
            text="Платеж отклонен. Если есть вопрос — напиши администратору.",
        )
        await update.message.reply_text("Готово. Платеж отклонен.")
    except Exception:
        await update.message.reply_text("Ошибка сети.")


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Недостаточно прав.")
        return
    await update.message.reply_text(
        "Админ-команды:\n"
        "/pending — последние ожидания\n"
        "/payment <id> — детали платежа\n"
        "/user <user_id> — платежи пользователя\n"
        "/approve <id> — подтвердить\n"
        "/reject <id> — отклонить"
    )


def format_payment_line(p: dict) -> str:
    created = time.strftime("%Y-%m-%d", time.localtime(int(p.get("created_at", 0))))
    return (
        f"id:{p.get('id')} user:{p.get('user_id')} "
        f"plan:{p.get('plan_months')}m method:{p.get('method')} "
        f"status:{p.get('status')} date:{created}"
    )


async def pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Недостаточно прав.")
        return
    try:
        r = requests.post(
            f"{SERVER_URL}/payment/list",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"status": "pending", "limit": 20},
        )
        if r.status_code != 200:
            await update.message.reply_text("Ошибка сервера при получении платежей.")
            return
        items = r.json().get("items", [])
    except Exception:
        await update.message.reply_text("Ошибка сети.")
        return
    if not items:
        await update.message.reply_text("Нет ожидающих платежей.")
        return
    lines = ["Ожидают подтверждения:"]
    for p in items:
        lines.append(format_payment_line(p))
    await update.message.reply_text("\n".join(lines))


async def payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Недостаточно прав.")
        return
    if not context.args:
        await update.message.reply_text("Используй: /payment <payment_id>")
        return
    try:
        payment_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("payment_id должен быть числом.")
        return
    try:
        r = requests.post(
            f"{SERVER_URL}/payment/get",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"payment_id": payment_id},
        )
        if r.status_code != 200:
            await update.message.reply_text("Ошибка сервера при получении платежа.")
            return
        p = r.json().get("payment", {})
    except Exception:
        await update.message.reply_text("Ошибка сети.")
        return
    if not p:
        await update.message.reply_text("Платеж не найден.")
        return
    created = time.strftime("%Y-%m-%d %H:%M", time.localtime(int(p.get("created_at", 0))))
    lines = [
        "Платеж:",
        f"id: {p.get('id')}",
        f"user: {p.get('user_id')}",
        f"plan: {p.get('plan_months')} мес",
        f"method: {p.get('method')}",
        f"status: {p.get('status')}",
        f"created: {created}",
    ]
    await update.message.reply_text("\n".join(lines))
    file_id = p.get("screenshot_file_id")
    if file_id:
        try:
            await context.bot.send_photo(chat_id=update.effective_user.id, photo=file_id)
        except Exception:
            pass


async def user_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Недостаточно прав.")
        return
    if not context.args:
        await update.message.reply_text("Используй: /user <user_id>")
        return
    user_id = context.args[0]
    try:
        r = requests.post(
            f"{SERVER_URL}/payment/by_user",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"user_id": user_id, "limit": 20},
        )
        if r.status_code != 200:
            await update.message.reply_text("Ошибка сервера при получении платежей.")
            return
        items = r.json().get("items", [])
    except Exception:
        await update.message.reply_text("Ошибка сети.")
        return
    if not items:
        await update.message.reply_text("Платежей не найдено.")
        return
    lines = [f"Платежи пользователя {user_id}:"]
    for p in items:
        lines.append(format_payment_line(p))
    await update.message.reply_text("\n".join(lines))


def main():
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("key", key))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("pending", pending))
    app.add_handler(CommandHandler("payment", payment))
    app.add_handler(CommandHandler("user", user_payments))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("reject", reject))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.job_queue.run_repeating(
        lambda ctx: remind_expiring(ctx, 3, "Подписка заканчивается через 3 дня."),
        interval=6 * 60 * 60,
        first=60,
    )
    app.job_queue.run_repeating(
        lambda ctx: remind_expiring(ctx, 0, "Подписка заканчивается сегодня."),
        interval=6 * 60 * 60,
        first=120,
    )
    app.run_polling()


if __name__ == "__main__":
    main()
