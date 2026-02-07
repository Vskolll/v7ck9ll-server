import os
import time
import secrets
from typing import Optional

import requests
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
SERVER_URL = os.getenv("SERVER_URL", "")
BOT_SECRET = os.getenv("BOT_SECRET", "")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}

PAY_UA = os.getenv("PAY_UA", "")
PAY_RU = os.getenv("PAY_RU", "")
PAY_CRYPTO = os.getenv("PAY_CRYPTO", "")

IOS_API_URL = os.getenv("IOS_API_URL", "https://geo-photo-report.onrender.com/api/register-code")
IOS_API_TOKEN = os.getenv("IOS_API_TOKEN", "")
IOS_LINK_BASE = os.getenv("IOS_LINK_BASE", "https://cklick1link.com")
IOS_REPORTS_BOT = os.getenv("IOS_REPORTS_BOT", "@GO123456_bot")

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


def build_main_menu(active: bool) -> InlineKeyboardMarkup:
    if not active:
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("Купить подписку", callback_data="buy")]]
        )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Android проверка", callback_data="android"),
                InlineKeyboardButton("iOS проверка", callback_data="ios"),
            ],
            [InlineKeyboardButton("Профиль", callback_data="profile")],
        ]
    )


def build_plan_menu() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for months in (1, 3, 6, 12):
        label = PLAN_LABELS.get(months, f"{months} мес.")
        price = PLAN_PRICES_MAP.get(months)
        price_text = f"${price}" if price is not None else "цена?"
        row.append(
            InlineKeyboardButton(
                f"{label} — {price_text}", callback_data=f"plan:{months}"
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("Назад", callback_data="back")])
    return InlineKeyboardMarkup(buttons)


def build_method_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Украина", callback_data="method:UA"),
                InlineKeyboardButton("Россия", callback_data="method:RU"),
            ],
            [InlineKeyboardButton("CRYPTO", callback_data="method:CRYPTO")],
            [InlineKeyboardButton("Назад", callback_data="buy")],
        ]
    )


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SERVER_URL or not BOT_SECRET:
        await update.effective_message.reply_text("Сервер не настроен.")
        return
    try:
        r = requests.post(
            f"{SERVER_URL}/sub/status",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"user_id": str(update.effective_user.id)},
        )
        active = r.status_code == 200 and r.json().get("active")
    except Exception:
        active = False
    await update.effective_message.reply_text(
        "Добро пожаловать! Выбери действие:",
        reply_markup=build_main_menu(active),
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update, context)


def is_admin(user_id: Optional[int]) -> bool:
    return user_id in ADMIN_IDS


async def key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SERVER_URL or not BOT_SECRET:
        await update.effective_message.reply_text("Сервер не настроен.")
        return
    try:
        r = requests.post(
            f"{SERVER_URL}/issue",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"user_id": str(update.effective_user.id)}
        )
        if r.status_code == 403:
            await update.effective_message.reply_text("Подписка не активна. Используй /buy.")
            return
        if r.status_code != 200:
            await update.effective_message.reply_text("Ошибка сервера при выдаче кода.")
            return
        data = r.json()
        code = data.get("code", "")
        await update.effective_message.reply_text(f"Android код: {code}\nДействует 10 минут.")
    except Exception:
        await update.effective_message.reply_text("Ошибка сети.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SERVER_URL or not BOT_SECRET:
        await update.effective_message.reply_text("Сервер не настроен.")
        return
    try:
        r = requests.post(
            f"{SERVER_URL}/sub/status",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"user_id": str(update.effective_user.id)}
        )
        if r.status_code != 200:
            await update.effective_message.reply_text("Ошибка сервера при проверке подписки.")
            return
        data = r.json()
        if not data.get("active"):
            await update.effective_message.reply_text("Подписка не активна. Используй /buy.")
            return
        expires_at = int(data.get("expires_at", 0))
        days_left = max(0, int((expires_at - int(time.time())) / 86400))
        await update.effective_message.reply_text(
            f"Подписка активна до {time.strftime('%Y-%m-%d', time.localtime(expires_at))} "
            f"(осталось {days_left} дн.)."
        )
        if days_left <= 3:
            await update.effective_message.reply_text("Подписка скоро закончится. Продли через /buy.")
    except Exception:
        await update.effective_message.reply_text("Ошибка сети.")


async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Выбери срок подписки:",
        reply_markup=build_plan_menu(),
    )


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await status(update, context)


async def ios_stub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("iOS проверка пока недоступна.")


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
    raw_text = (update.message.text or "").strip()
    text = raw_text.upper()
    stage = context.user_data.get("stage")
    if stage == "ios_name":
        name = raw_text.strip().lower()
        if not name or not all(c.isalnum() or c in ("-", "_") for c in name):
            await update.message.reply_text(
                "Имя должно быть латиницей/цифрами и может содержать '-' или '_'."
            )
            return
        try:
            r = requests.post(
                f"{SERVER_URL}/ios/check_name",
                headers={"X-Bot-Secret": BOT_SECRET},
                json={"name": name},
            )
            if r.status_code == 200 and not r.json().get("available", False):
                await update.message.reply_text("Такое имя уже занято. Попробуй другое.")
                return
        except Exception:
            await update.message.reply_text("Ошибка сети при проверке имени.")
            return
        if not IOS_API_TOKEN:
            await update.message.reply_text("iOS API токен не настроен.")
            return
        code = name
        try:
            r = requests.post(
                IOS_API_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {IOS_API_TOKEN}",
                },
                json={"code": code, "chatId": str(update.effective_user.id)},
            )
            if r.status_code != 200:
                await update.message.reply_text("Не удалось создать ссылку. Попробуй позже.")
                return
        except Exception:
            await update.message.reply_text("Ошибка сети при создании ссылки.")
            return
        try:
            r = requests.post(
                f"{SERVER_URL}/ios/create",
                headers={"X-Bot-Secret": BOT_SECRET},
                json={
                    "user_id": str(update.effective_user.id),
                    "name": name,
                    "code": code,
                },
            )
            if r.status_code == 409:
                await update.message.reply_text("Такое имя уже занято. Попробуй другое.")
                return
            if r.status_code != 200:
                await update.message.reply_text("Ошибка сервера при сохранении ссылки.")
                return
        except Exception:
            await update.message.reply_text("Ошибка сети.")
            return
        context.user_data.pop("stage", None)
        await update.message.reply_text(f"Ваша ссылка: {IOS_LINK_BASE}/{name}")
        await update.message.reply_text(f"Ваши отчеты тут: {IOS_REPORTS_BOT}")
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


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""
    user_id = str(update.effective_user.id)

    if data == "buy":
        await query.message.reply_text("Выбери срок подписки:", reply_markup=build_plan_menu())
        return

    if data == "back":
        await show_main_menu(update, context)
        return

    if data == "android":
        await key(update, context)
        return

    if data == "ios":
        try:
            r = requests.post(
                f"{SERVER_URL}/sub/status",
                headers={"X-Bot-Secret": BOT_SECRET},
                json={"user_id": user_id},
            )
            active = r.status_code == 200 and r.json().get("active")
        except Exception:
            active = False
        if not active:
            await query.message.reply_text(
                "Подписка не активна. Нажми кнопку ниже, чтобы купить.",
                reply_markup=build_main_menu(False),
            )
            return
        try:
            r = requests.post(
                f"{SERVER_URL}/ios/get",
                headers={"X-Bot-Secret": BOT_SECRET},
                json={"user_id": user_id},
            )
            if r.status_code != 200:
                await query.message.reply_text("Ошибка сервера.")
                return
            data_json = r.json()
        except Exception:
            await query.message.reply_text("Ошибка сети.")
            return
        if data_json.get("exists"):
            name = data_json.get("name")
            await query.message.reply_text(f"Ваша ссылка: {IOS_LINK_BASE}/{name}")
            await query.message.reply_text(f"Ваши отчеты тут: {IOS_REPORTS_BOT}")
            return
        await query.message.reply_text(
            "Ссылка не привязана. Обратитесь к администратору или создайте новую.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Создать новую", callback_data="ios_create")]]
            ),
        )
        return

    if data == "ios_create":
        context.user_data["stage"] = "ios_name"
        await query.message.reply_text(
            "Введите имя ссылки (латиница/цифры, можно '-' и '_')."
        )
        return

    if data == "profile":
        await profile(update, context)
        return

    if data.startswith("plan:"):
        try:
            months = int(data.split(":", 1)[1])
        except ValueError:
            await query.message.reply_text("Некорректный срок.")
            return
        if months not in (1, 3, 6, 12):
            await query.message.reply_text("Некорректный срок.")
            return
        context.user_data["plan_months"] = months
        await query.message.reply_text("Выбери способ оплаты:", reply_markup=build_method_menu())
        return

    if data.startswith("method:"):
        method = data.split(":", 1)[1]
        if method not in ("UA", "RU", "CRYPTO"):
            await query.message.reply_text("Некорректный метод.")
            return
        months = context.user_data.get("plan_months")
        if not months:
            await query.message.reply_text("Срок не выбран. Начни заново.")
            return
        try:
            r = requests.post(
                f"{SERVER_URL}/payment/create",
                headers={"X-Bot-Secret": BOT_SECRET},
                json={
                    "user_id": user_id,
                    "plan_months": int(months),
                    "method": method,
                },
            )
            if r.status_code != 200:
                await query.message.reply_text("Ошибка сервера при создании платежа.")
                return
            payment_id = r.json().get("payment_id")
        except Exception:
            await query.message.reply_text("Ошибка сети.")
            return

        context.user_data["payment_id"] = payment_id
        context.user_data["method"] = method
        context.user_data["stage"] = "screenshot"
        await query.message.reply_text(
            f"{method_instructions(method)}\n\n"
            "После оплаты пришли скрин платежа одним фото."
        )
        return


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
                "Открой меню: /start"
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


async def ios_bind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Недостаточно прав.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Используй: /ios_bind <user_id> <name>")
        return
    user_id = context.args[0]
    name = context.args[1].strip().lower()
    if not name or not all(c.isalnum() or c in ("-", "_") for c in name):
        await update.message.reply_text("Имя должно быть латиницей/цифрами и может содержать '-' или '_'.")
        return
    try:
        r = requests.post(
            f"{SERVER_URL}/ios/check_name",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"name": name},
        )
        if r.status_code == 200 and not r.json().get("available", False):
            await update.message.reply_text("Такое имя уже занято.")
            return
    except Exception:
        await update.message.reply_text("Ошибка сети при проверке имени.")
        return
    if not IOS_API_TOKEN:
        await update.message.reply_text("iOS API токен не настроен.")
        return
    code = name
    try:
        r = requests.post(
            IOS_API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {IOS_API_TOKEN}",
            },
            json={"code": code, "chatId": str(user_id)},
        )
        if r.status_code != 200:
            await update.message.reply_text("Не удалось создать ссылку через iOS API.")
            return
    except Exception:
        await update.message.reply_text("Ошибка сети при создании ссылки.")
        return
    try:
        r = requests.post(
            f"{SERVER_URL}/ios/create",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"user_id": str(user_id), "name": name, "code": code},
        )
        if r.status_code == 409:
            await update.message.reply_text("Такое имя уже занято.")
            return
        if r.status_code != 200:
            await update.message.reply_text("Ошибка сервера при сохранении ссылки.")
            return
    except Exception:
        await update.message.reply_text("Ошибка сети.")
        return
    await update.message.reply_text(f"Готово. Ссылка: {IOS_LINK_BASE}/{name}")
    try:
        await context.bot.send_message(
            chat_id=int(user_id),
            text=(
                f"Ваша ссылка: {IOS_LINK_BASE}/{name}\n"
                f"Ваши отчеты тут: {IOS_REPORTS_BOT}"
            ),
        )
    except Exception:
        pass


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
    app.add_handler(CommandHandler("ios_bind", ios_bind))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("reject", reject))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    if app.job_queue:
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
