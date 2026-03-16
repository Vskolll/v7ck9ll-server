import os
import time
import secrets
from typing import Optional

import requests
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    BotCommand,
    MenuButtonCommands,
    BotCommandScopeChat,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
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

IOS_LINK_BASE = os.getenv("IOS_LINK_BASE", "https://cklick1link.com")
IOS_API_BASE = os.getenv("IOS_API_BASE", IOS_LINK_BASE).rstrip("/")
IOS_API_URL = os.getenv("IOS_API_URL", f"{IOS_API_BASE}/api/register-code")
IOS_API_TOKEN = os.getenv("IOS_API_TOKEN", "")
IOS_ACCESS_API_URL = os.getenv("IOS_ACCESS_API_URL", f"{IOS_API_BASE}/api/register-temp-code")
IOS_ACCESS_CODE_TTL = int(os.getenv("IOS_ACCESS_CODE_TTL", "600"))
IOS_REPORTS_BOT = os.getenv("IOS_REPORTS_BOT", "@GO123456_bot")
APK_PATH = os.getenv("APK_PATH", os.path.join(os.path.dirname(__file__), "app-V7ck9ll.apk"))
ANDROID_APP_LINK = os.getenv("ANDROID_APP_LINK", "https://t.me/ANDROIDAPPKK")
ANDROID_INSTRUCTION_URL = os.getenv("ANDROID_INSTRUCTION_URL", "https://t.me/V7ck9ll_Checker/3")
IOS_INSTRUCTION_URL = os.getenv("IOS_INSTRUCTION_URL", "https://t.me/V7ck9ll_Checker/2")
INLINE_HTTP_TIMEOUT = float(os.getenv("INLINE_HTTP_TIMEOUT", "2.5"))

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
            [[InlineKeyboardButton("💎 Купить подписку", callback_data="buy")]]
        )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✨ Android проверка", callback_data="android"),
                InlineKeyboardButton("🍏 iOS проверка", callback_data="ios"),
            ],
            [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
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
                f"{label} - {price_text}", callback_data=f"plan:{months}"
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


def build_ios_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔑 Получить код доступа (10 мин)", callback_data="ios_access_code")],
            [InlineKeyboardButton("🔎 Проверить по моему ID", callback_data="ios_self")],
            [InlineKeyboardButton("📘 Получить инструкцию", url=IOS_INSTRUCTION_URL)],
            [InlineKeyboardButton("Назад", callback_data="back")],
        ]
    )


def build_android_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔑 Получить код", callback_data="android_code")],
            [InlineKeyboardButton("📦 Получить приложение", callback_data="android_app")],
            [InlineKeyboardButton("📘 Инструкция", url=ANDROID_INSTRUCTION_URL)],
            [InlineKeyboardButton("Назад", callback_data="back")],
        ]
    )


def build_admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📅 Подписки", callback_data="admin_subs:0")],
            [InlineKeyboardButton("🧾 Ожидающие платежи", callback_data="admin_pending")],
            [InlineKeyboardButton("🔄 Обновить", callback_data="admin_home")],
        ]
    )


def build_rental_platform_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Android", callback_data="rental_android"),
                InlineKeyboardButton("iOS", callback_data="rental_ios"),
            ]
        ]
    )


def markdown_escape(value: str) -> str:
    escaped = str(value or "")
    for ch in ("\\", "_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"):
        escaped = escaped.replace(ch, f"\\{ch}")
    return escaped


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SERVER_URL or not BOT_SECRET:
        await update.effective_message.reply_text("Сервер не настроен.")
        return
    active, _ = get_subscription_state(str(update.effective_user.id))
    await sync_chat_commands(context, int(update.effective_user.id), active is True)
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
    user_id = str(update.effective_user.id)
    active, _ = get_subscription_state(user_id)
    await sync_chat_commands(context, int(update.effective_user.id), active is True)
    if active is False:
        await update.effective_message.reply_text("Подписка не активна. Используй /buy.")
        return

    raw_mode = (context.args[0] if context.args else "").strip().lower()
    if not raw_mode:
        await update.effective_message.reply_text(
            "Укажи платформу:\n"
            "/key android - получить Android код\n"
            "/key ios - получить iOS код доступа"
        )
        return
    if raw_mode in ("ios", "apple", "айос", "иоs"):
        await issue_ios_access_code(update, context)
        return
    if raw_mode in ("android", "droid", "андроид"):
        await issue_android_access_code(update, context, user_id=user_id)
        return
    else:
        await update.effective_message.reply_text(
            "Используй:\n"
            "/key android - получить Android код\n"
            "/key ios - получить iOS код доступа"
        )
        return


async def issue_android_access_code(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: Optional[str] = None,
):
    uid = user_id or str(update.effective_user.id)
    try:
        r = requests.post(
            f"{SERVER_URL}/issue",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"user_id": uid}
        )
        if r.status_code == 403:
            await update.effective_message.reply_text("Подписка не активна. Используй /buy.")
            return
        if r.status_code != 200:
            await update.effective_message.reply_text("Ошибка сервера при выдаче кода.")
            return
        data = r.json()
        code = data.get("code", "")
        await update.effective_message.reply_text(
            "Android код доступа:\n"
            f"`{code}`\n\n"
            "Скопируй код и введи в приложении.\n"
            "Код действует 10 минут.",
            parse_mode="Markdown",
        )
    except Exception:
        await update.effective_message.reply_text("Ошибка сети.")


def fetch_android_access_code(user_id: str) -> tuple[Optional[str], Optional[str]]:
    try:
        r = requests.post(
            f"{SERVER_URL}/issue",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"user_id": user_id},
            timeout=INLINE_HTTP_TIMEOUT,
        )
        if r.status_code == 403:
            return None, "Подписка не активна. Используй /buy."
        if r.status_code != 200:
            return None, "Ошибка сервера при выдаче кода."
        code = (r.json().get("code") or "").strip()
        if not code:
            return None, "Сервер вернул пустой код."
        return code, None
    except Exception:
        return None, "Ошибка сети."


def fetch_ios_link_by_user_id(user_id: str) -> tuple[Optional[str], Optional[str]]:
    try:
        r = requests.post(
            f"{SERVER_URL}/ios/get",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"user_id": user_id},
            timeout=INLINE_HTTP_TIMEOUT,
        )
        if r.status_code != 200:
            return None, "Ошибка сервера."
        data = r.json()
    except Exception:
        return None, "Ошибка сети."

    if not data.get("exists"):
        return None, "iOS ссылка не привязана к вашему ID."
    name = (data.get("name") or "").strip()
    if not name:
        return None, "iOS ссылка не найдена."
    return f"{IOS_LINK_BASE}/{name}", None


def fetch_ios_access_code(user_id: str) -> tuple[Optional[str], Optional[str]]:
    if not IOS_API_TOKEN:
        return None, "IOS_API_TOKEN не настроен."
    try:
        r = requests.post(
            IOS_ACCESS_API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {IOS_API_TOKEN}",
            },
            json={
                "chatId": user_id,
                "ttlSeconds": IOS_ACCESS_CODE_TTL,
            },
            timeout=INLINE_HTTP_TIMEOUT,
        )
        if r.status_code != 200:
            return None, "Не удалось выдать iOS код. Попробуй позже."
        code = (r.json().get("code") or "").strip()
        if not code:
            return None, "Сервер вернул пустой код."
        return code, None
    except Exception:
        return None, "Ошибка сети при выдаче iOS кода."


async def send_rental_android_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str):
    code, error = fetch_android_access_code(user_id)
    if error:
        await update.effective_message.reply_text(error)
        return
    await update.effective_message.reply_text(
        "Спасибо, что взяли аренду.\n\n"
        "Чтобы пройти проверку,\n"
        f"скачайте это приложение:\n{ANDROID_APP_LINK}\n\n"
        f"Ваш код: {code}\n\n"
        "Спасибо за выбор нашей аренды."
    )


async def send_rental_ios_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str):
    ios_link, link_error = fetch_ios_link_by_user_id(user_id)
    if link_error:
        await update.effective_message.reply_text(link_error)
        return
    code, code_error = fetch_ios_access_code(user_id)
    if code_error:
        await update.effective_message.reply_text(code_error)
        return
    await update.effective_message.reply_text(
        "Спасибо, что взяли аренду.\n\n"
        "Чтобы пройти проверку,\n"
        f"перейдите по данной ссылке:\n{ios_link}\n\n"
        f"Ваш код: {code}\n\n"
        "Спасибо за выбор нашей аренды."
    )


def build_android_inline_message(code: str) -> str:
    return (
        "Спасибо, что взяли аренду.\n\n"
        "Чтобы пройти проверку, скачайте это приложение:\n"
        f"{ANDROID_APP_LINK}\n\n"
        "Ваш код:\n\n"
        f"`{markdown_escape(code)}`\n\n"
        "Спасибо за выбор нашей аренды."
    )


def build_ios_inline_message(ios_link: str, code: str) -> str:
    return (
        "Спасибо, что взяли аренду.\n\n"
        "Чтобы пройти проверку, перейдите по данной ссылке:\n"
        f"{ios_link}\n\n"
        "Ваш код:\n\n"
        f"`{markdown_escape(code)}`\n\n"
        "Спасибо за выбор нашей аренды."
    )


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    if not query:
        return

    user = query.from_user
    user_id = str(user.id)
    active, _ = get_subscription_state(user_id)

    if active is False:
        await query.answer(
            [
                InlineQueryResultArticle(
                    id=f"inactive:{user_id}",
                    title="Подписка не активна",
                    description="Перейдите в бот и оформите аренду.",
                    input_message_content=InputTextMessageContent(
                        "У вас нет активной подписки.\nПерейдите в бот и оформите аренду."
                    ),
                )
            ],
            cache_time=0,
            is_personal=True,
        )
        return

    if active is None:
        await query.answer(
            [
                InlineQueryResultArticle(
                    id=f"network:{user_id}",
                    title="Ошибка проверки подписки",
                    description="Попробуйте еще раз через пару секунд.",
                    input_message_content=InputTextMessageContent(
                        "Не удалось проверить подписку. Попробуйте еще раз через пару секунд."
                    ),
                )
            ],
            cache_time=0,
            is_personal=True,
        )
        return

    now_id = int(time.time())
    results = []

    android_code, android_error = fetch_android_access_code(user_id)
    if android_code and not android_error:
        results.append(
            InlineQueryResultArticle(
                id=f"android:{user_id}:{now_id}",
                title="Android",
                description="Сообщение с Android-ссылкой и вашим кодом",
                input_message_content=InputTextMessageContent(
                    build_android_inline_message(android_code),
                    parse_mode="MarkdownV2",
                ),
            )
        )
    else:
        results.append(
            InlineQueryResultArticle(
                id=f"android-fallback:{user_id}:{now_id}",
                title="Android",
                description="Выбор доступен, код попробуйте обновить еще раз",
                input_message_content=InputTextMessageContent(
                    "Android временно недоступен.\n"
                    "Попробуйте еще раз через пару секунд или откройте бота напрямую."
                ),
            )
        )

    ios_link, ios_link_error = fetch_ios_link_by_user_id(user_id)
    ios_code, ios_code_error = fetch_ios_access_code(user_id)
    if ios_link and ios_code and not ios_link_error and not ios_code_error:
        results.append(
            InlineQueryResultArticle(
                id=f"ios:{user_id}:{now_id}",
                title="iOS",
                description="Сообщение с персональной iOS-ссылкой и вашим кодом",
                input_message_content=InputTextMessageContent(
                    build_ios_inline_message(ios_link, ios_code),
                    parse_mode="MarkdownV2",
                ),
            )
        )
    else:
        results.append(
            InlineQueryResultArticle(
                id=f"ios-fallback:{user_id}:{now_id}",
                title="iOS",
                description="Выбор доступен, данные попробуйте обновить еще раз",
                input_message_content=InputTextMessageContent(
                    "iOS временно недоступен.\n"
                    "Попробуйте еще раз через пару секунд или откройте бота напрямую."
                ),
            )
        )

    await query.answer(results, cache_time=0, is_personal=True)


async def key_android(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SERVER_URL or not BOT_SECRET:
        await update.effective_message.reply_text("Сервер не настроен.")
        return
    user_id = str(update.effective_user.id)
    active, _ = get_subscription_state(user_id)
    await sync_chat_commands(context, int(update.effective_user.id), active is True)
    if active is False:
        await update.effective_message.reply_text("Подписка не активна. Используй /buy.")
        return
    await issue_android_access_code(update, context, user_id=user_id)


async def key_ios(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SERVER_URL or not BOT_SECRET:
        await update.effective_message.reply_text("Сервер не настроен.")
        return
    user_id = str(update.effective_user.id)
    active, _ = get_subscription_state(user_id)
    await sync_chat_commands(context, int(update.effective_user.id), active is True)
    if active is False:
        await update.effective_message.reply_text("Подписка не активна. Используй /buy.")
        return
    await issue_ios_access_code(update, context)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SERVER_URL or not BOT_SECRET:
        await update.effective_message.reply_text("Сервер не настроен.")
        return
    user_id = str(update.effective_user.id)
    active, expires_at = get_subscription_state(user_id)
    await sync_chat_commands(context, int(update.effective_user.id), active is True)
    if active is False:
        await update.effective_message.reply_text("Подписка не активна. Используй /buy.")
        return
    if active is None:
        await update.effective_message.reply_text("Ошибка сети при проверке подписки.")
        return
    days_left = max(0, int((expires_at - int(time.time())) / 86400))
    await update.effective_message.reply_text(
        f"Подписка активна до {time.strftime('%Y-%m-%d', time.localtime(expires_at))} "
        f"(осталось {days_left} дн.)."
    )
    if days_left <= 3:
        await update.effective_message.reply_text("Подписка скоро закончится. Продли через /buy.")


def get_subscription_state(user_id: str) -> tuple[Optional[bool], int]:
    try:
        r = requests.post(
            f"{SERVER_URL}/sub/status",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"user_id": user_id},
            timeout=INLINE_HTTP_TIMEOUT,
        )
        if r.status_code != 200:
            return None, 0
        data = r.json()
        if not data.get("active"):
            return False, 0
        expires_at = int(data.get("expires_at", 0))
        return expires_at > int(time.time()), expires_at
    except Exception:
        return None, 0


async def sync_chat_commands(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, active: bool
) -> None:
    commands = [
        BotCommand("start", "Начать 🚀"),
        BotCommand("status", "Проверить подписку"),
        BotCommand("key_android", "Кей Android"),
        BotCommand("key_ios", "Кей iOS"),
    ]
    if not active:
        commands.append(BotCommand("buy", "Купить подписку"))
    try:
        await context.bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id))
    except Exception:
        pass


async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Выбери срок подписки:",
        reply_markup=build_plan_menu(),
    )


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await status(update, context)


async def ios_stub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("iOS проверка пока недоступна.")


def method_instructions(method: str, amount: Optional[int]) -> str:
    amount_text = f"Сумма к оплате: ${amount}" if amount is not None else "Сумма к оплате: уточнить"
    if method == "UA" and PAY_UA:
        return f"{amount_text}\nРеквизиты Украина:\n{PAY_UA}"
    if method == "RU" and PAY_RU:
        return f"{amount_text}\nРеквизиты Россия:\n{PAY_RU}"
    if method == "CRYPTO" and PAY_CRYPTO:
        return f"{amount_text}\nРеквизиты CRYPTO:\n{PAY_CRYPTO}"
    return "Реквизиты пока не настроены."


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    raw_text = (update.message.text or "").strip()
    text = raw_text.upper()
    stage = context.user_data.get("stage")
    if stage == "admin_sub_days":
        if not is_admin(update.effective_user.id):
            context.user_data.pop("stage", None)
            context.user_data.pop("admin_target_user", None)
            await update.message.reply_text("Недостаточно прав.")
            return
        target_user = str(context.user_data.get("admin_target_user") or "").strip()
        if not target_user:
            context.user_data.pop("stage", None)
            await update.message.reply_text("Целевой user_id не найден. Открой /admin заново.")
            return
        try:
            days = int(raw_text.strip())
        except ValueError:
            await update.message.reply_text("Введи целое число дней (например: 30).")
            return
        if days < 0 or days > 3650:
            await update.message.reply_text("Допустимо от 0 до 3650 дней.")
            return
        try:
            r = requests.post(
                f"{SERVER_URL}/sub/set_days",
                headers={"X-Bot-Secret": BOT_SECRET},
                json={"user_id": target_user, "days": days},
                timeout=10,
            )
            if r.status_code != 200:
                await update.message.reply_text("Ошибка сервера при обновлении дней.")
                return
            data = r.json()
        except Exception:
            await update.message.reply_text("Ошибка сети.")
            return

        context.user_data.pop("stage", None)
        context.user_data.pop("admin_target_user", None)

        if data.get("removed"):
            await update.message.reply_text(
                f"✅ Подписка для `{target_user}` удалена (0 дней).",
                parse_mode="Markdown",
            )
        else:
            expires_at = int(data.get("expires_at") or 0)
            days_left = max(0, int((expires_at - int(time.time())) / 86400))
            until = time.strftime("%Y-%m-%d %H:%M", time.localtime(expires_at))
            await update.message.reply_text(
                f"✅ Обновлено для `{target_user}`\n"
                f"⏳ Осталось: *{days_left} дн*\n"
                f"📆 До: *{until}*",
                parse_mode="Markdown",
                reply_markup=build_admin_user_keyboard(target_user),
            )
        return

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

    if raw_text == "@":
        if not SERVER_URL or not BOT_SECRET:
            await update.message.reply_text("Сервер не настроен.")
            return
        user_id = str(update.effective_user.id)
        active, _ = get_subscription_state(user_id)
        await sync_chat_commands(context, int(update.effective_user.id), active is True)
        if active is False:
            await update.message.reply_text("Подписка не активна. Используй /buy.")
            return
        if active is None:
            await update.message.reply_text("Ошибка сети при проверке подписки.")
            return
        await update.message.reply_text(
            "Выбери платформу:",
            reply_markup=build_rental_platform_menu(),
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


async def handle_ios_check(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: str):
    try:
        r = requests.post(
            f"{SERVER_URL}/ios/get",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"user_id": str(chat_id)},
        )
        if r.status_code != 200:
            await update.effective_message.reply_text("Ошибка сервера.")
            return
        data_json = r.json()
    except Exception:
        await update.effective_message.reply_text("Ошибка сети.")
        return
    if data_json.get("exists"):
        name = data_json.get("name")
        await update.effective_message.reply_text(f"Ваша ссылка: {IOS_LINK_BASE}/{name}")
        await update.effective_message.reply_text(f"Ваши отчеты тут: {IOS_REPORTS_BOT}")
        return
    await update.effective_message.reply_text(
        "Ссылка не привязана. Обратитесь к администратору или создайте новую.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Создать новую", callback_data="ios_create")]]
        ),
    )


async def issue_ios_access_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not IOS_API_TOKEN:
        await update.effective_message.reply_text("IOS_API_TOKEN не настроен.")
        return
    try:
        r = requests.post(
            IOS_ACCESS_API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {IOS_API_TOKEN}",
            },
            json={
                "chatId": str(update.effective_user.id),
                "ttlSeconds": IOS_ACCESS_CODE_TTL,
            },
            timeout=15,
        )
        if r.status_code != 200:
            await update.effective_message.reply_text("Не удалось выдать iOS код. Попробуй позже.")
            return
        data = r.json()
    except Exception:
        await update.effective_message.reply_text("Ошибка сети при выдаче iOS кода.")
        return

    code = data.get("code")
    if not code:
        await update.effective_message.reply_text("Сервер вернул пустой код.")
        return

    expires_at = int(data.get("expiresAt") or 0)
    ttl_seconds = int(data.get("ttlSeconds") or IOS_ACCESS_CODE_TTL)
    if expires_at > 0:
        exp_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expires_at / 1000))
        exp_line = f"Истекает: {exp_str} (локальное время сервера), TTL: {ttl_seconds} сек."
    else:
        exp_line = f"TTL: {ttl_seconds} сек."

    await update.effective_message.reply_text(
        "iOS код доступа:\n"
        f"`{code}`\n\n"
        f"{exp_line}\n"
        f"Проверочный URL: {IOS_LINK_BASE}\n\n"
        "Открой сайт, введи код и нажми 'Активировать'.\n"
        "Доступ для устройства выдается на 10 минут.",
        parse_mode="Markdown",
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""
    user_id = str(update.effective_user.id)

    async def safe_edit_or_reply(
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        parse_mode: Optional[str] = None,
    ):
        try:
            await query.message.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
        except Exception:
            await query.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )

    if data.startswith("admin_"):
        if not is_admin(update.effective_user.id):
            await query.message.reply_text("Недостаточно прав.")
            return

        if data == "admin_home":
            await safe_edit_or_reply(
                "⚙️ Админ-панель\nВыбери действие:",
                reply_markup=build_admin_menu(),
            )
            return

        if data == "admin_pending":
            try:
                r = requests.post(
                    f"{SERVER_URL}/payment/list",
                    headers={"X-Bot-Secret": BOT_SECRET},
                    json={"status": "pending", "limit": 20},
                    timeout=10,
                )
                if r.status_code != 200:
                    await query.message.reply_text("Ошибка сервера при получении платежей.")
                    return
                items = r.json().get("items", [])
            except Exception:
                await query.message.reply_text("Ошибка сети.")
                return
            if not items:
                await safe_edit_or_reply(
                    "🧾 Ожидающих платежей нет.",
                    reply_markup=build_admin_menu(),
                )
                return
            lines = ["🧾 Ожидают подтверждения:"]
            for p in items:
                lines.append(format_payment_line(p))
            await safe_edit_or_reply("\n".join(lines), reply_markup=build_admin_menu())
            return

        if data.startswith("admin_subs:"):
            try:
                page = max(0, int(data.split(":", 1)[1]))
            except Exception:
                page = 0
            items = fetch_active_subscriptions()
            if not items:
                await safe_edit_or_reply(
                    "📅 Активных подписок не найдено.",
                    reply_markup=build_admin_menu(),
                )
                return
            page_size = 8
            total_pages = max(1, (len(items) + page_size - 1) // page_size)
            page = min(page, total_pages - 1)
            start = page * page_size
            chunk = items[start:start + page_size]
            lines = [f"📅 Подписки - стр. {page + 1}/{total_pages}", ""]
            for i, it in enumerate(chunk, start=1 + start):
                until = time.strftime("%Y-%m-%d", time.localtime(int(it["expires_at"])))
                lines.append(
                    f"{i}. 👤 `{it['user_id']}`\n"
                    f"   ⏳ Осталось: *{it['days_left']} дн*\n"
                    f"   📆 До: *{until}*"
                )
            await safe_edit_or_reply(
                "\n".join(lines),
                parse_mode="Markdown",
                reply_markup=build_admin_subs_keyboard(items, page, page_size=page_size),
            )
            return

        if data.startswith("admin_sub_user:"):
            target_user = data.split(":", 1)[1].strip()
            if not target_user:
                await query.message.reply_text("Некорректный user_id.")
                return
            txt = (
                f"👤 user_id: `{target_user}`\n"
                "Выбери действие ниже:"
            )
            await safe_edit_or_reply(
                txt,
                parse_mode="Markdown",
                reply_markup=build_admin_user_keyboard(target_user),
            )
            return

        if data.startswith("admin_user_pay:"):
            target_user = data.split(":", 1)[1].strip()
            if not target_user:
                await query.message.reply_text("Некорректный user_id.")
                return
            try:
                r = requests.post(
                    f"{SERVER_URL}/payment/by_user",
                    headers={"X-Bot-Secret": BOT_SECRET},
                    json={"user_id": target_user, "limit": 20},
                    timeout=10,
                )
                if r.status_code != 200:
                    await query.message.reply_text("Ошибка сервера при получении платежей.")
                    return
                items = r.json().get("items", [])
            except Exception:
                await query.message.reply_text("Ошибка сети.")
                return
            if not items:
                await safe_edit_or_reply(
                    f"🧾 Платежей у `{target_user}` не найдено.",
                    parse_mode="Markdown",
                    reply_markup=build_admin_user_keyboard(target_user),
                )
                return
            lines = [f"🧾 Платежи `{target_user}`:"]
            for p in items:
                lines.append(format_payment_line(p))
            await safe_edit_or_reply(
                "\n".join(lines),
                parse_mode="Markdown",
                reply_markup=build_admin_user_keyboard(target_user),
            )
            return

        if data.startswith("admin_sub_edit:"):
            target_user = data.split(":", 1)[1].strip()
            if not target_user:
                await query.message.reply_text("Некорректный user_id.")
                return
            context.user_data["stage"] = "admin_sub_days"
            context.user_data["admin_target_user"] = target_user
            await query.message.reply_text(
                f"✏️ Введи новое количество дней для `{target_user}`.\n"
                "0 - удалить подписку, 30 - месяц и т.д.",
                parse_mode="Markdown",
            )
            return

        if data.startswith("admin_sub_remove:"):
            target_user = data.split(":", 1)[1].strip()
            if not target_user:
                await query.message.reply_text("Некорректный user_id.")
                return
            try:
                r = requests.post(
                    f"{SERVER_URL}/sub/remove",
                    headers={"X-Bot-Secret": BOT_SECRET},
                    json={"user_id": target_user},
                    timeout=10,
                )
                if r.status_code != 200:
                    await query.message.reply_text("Ошибка сервера при удалении подписки.")
                    return
                result = r.json()
            except Exception:
                await query.message.reply_text("Ошибка сети.")
                return
            if result.get("removed"):
                await safe_edit_or_reply(
                    f"✅ Подписка пользователя `{target_user}` удалена.",
                    parse_mode="Markdown",
                    reply_markup=build_admin_user_keyboard(target_user),
                )
            else:
                await safe_edit_or_reply(
                    f"ℹ️ У пользователя `{target_user}` нет активной подписки.",
                    parse_mode="Markdown",
                    reply_markup=build_admin_user_keyboard(target_user),
                )
            return

    if data == "buy":
        await query.message.reply_text("Выбери срок подписки:", reply_markup=build_plan_menu())
        return

    if data == "back":
        await show_main_menu(update, context)
        return

    if data == "android":
        await query.message.reply_text(
            "Выбери действие для Android:",
            reply_markup=build_android_menu(),
        )
        return

    if data == "rental_android":
        active, _ = get_subscription_state(user_id)
        if active is False:
            await query.message.reply_text("Подписка не активна. Используй /buy.")
            return
        if active is None:
            await query.message.reply_text("Ошибка сети при проверке подписки.")
            return
        await send_rental_android_message(update, context, user_id)
        return

    if data == "android_code":
        await key(update, context)
        return

    if data == "android_app":
        if not os.path.exists(APK_PATH):
            await query.message.reply_text("APK не найден на сервере.")
            return
        try:
            with open(APK_PATH, "rb") as f:
                await context.bot.send_document(
                    chat_id=update.effective_user.id,
                    document=f,
                    filename=os.path.basename(APK_PATH),
                )
        except Exception:
            await query.message.reply_text("Не удалось отправить APK.")
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
        await query.message.reply_text(
            "Выбери вариант проверки iOS:",
            reply_markup=build_ios_menu(),
        )
        return

    if data == "rental_ios":
        active, _ = get_subscription_state(user_id)
        if active is False:
            await query.message.reply_text("Подписка не активна. Используй /buy.")
            return
        if active is None:
            await query.message.reply_text("Ошибка сети при проверке подписки.")
            return
        await send_rental_ios_message(update, context, user_id)
        return

    if data == "ios_self":
        await handle_ios_check(update, context, user_id)
        return

    if data == "ios_access_code":
        await issue_ios_access_code(update, context)
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
        amount = PLAN_PRICES_MAP.get(int(months))
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
            f"{method_instructions(method, amount)}\n\n"
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


def fetch_active_subscriptions(days_window: int = 3650) -> list[dict]:
    now = int(time.time())
    try:
        r = requests.post(
            f"{SERVER_URL}/sub/expiring",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"days": days_window},
            timeout=15,
        )
        if r.status_code != 200:
            return []
        items = r.json().get("items", [])
    except Exception:
        return []

    out = []
    for item in items:
        user_id = str(item.get("user_id") or "").strip()
        expires_at = int(item.get("expires_at") or 0)
        if not user_id or expires_at <= now:
            continue
        days_left = max(0, int((expires_at - now) / 86400))
        out.append(
            {
                "user_id": user_id,
                "expires_at": expires_at,
                "days_left": days_left,
            }
        )
    out.sort(key=lambda x: x["expires_at"])
    return out


def parse_sub_set_lines(raw_text: str) -> tuple[list[tuple[str, int]], list[str]]:
    items: list[tuple[str, int]] = []
    errors: list[str] = []

    for idx, line in enumerate(raw_text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "/sub_set":
            parts = parts[1:]
        if len(parts) != 2:
            errors.append(f"Строка {idx}: нужен формат /sub_set <user_id> <days>")
            continue

        target_user = parts[0].strip()
        try:
            days = int(parts[1].strip())
        except ValueError:
            errors.append(f"Строка {idx}: days должен быть целым числом")
            continue

        if days < 0 or days > 3650:
            errors.append(f"Строка {idx}: days должен быть в диапазоне 0..3650")
            continue

        items.append((target_user, days))

    return items, errors


def set_subscription_days(target_user: str, days: int) -> tuple[bool, str]:
    try:
        r = requests.post(
            f"{SERVER_URL}/sub/set_days",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"user_id": target_user, "days": days},
            timeout=10,
        )
        if r.status_code != 200:
            return False, f"{target_user}: ошибка сервера"
        data = r.json()
    except Exception:
        return False, f"{target_user}: ошибка сети"

    if data.get("removed"):
        return True, f"{target_user}: подписка удалена"

    expires_at = int(data.get("expires_at") or 0)
    days_left = max(0, int((expires_at - int(time.time())) / 86400))
    until = time.strftime("%Y-%m-%d %H:%M", time.localtime(expires_at))
    return True, f"{target_user}: {days_left} дн., до {until}"


def build_admin_subs_keyboard(items: list[dict], page: int, page_size: int = 8) -> InlineKeyboardMarkup:
    start = page * page_size
    chunk = items[start:start + page_size]
    rows = []
    for it in chunk:
        rows.append(
            [
                InlineKeyboardButton(
                    f"👤 {it['user_id']} • {it['days_left']} дн",
                    callback_data=f"admin_sub_user:{it['user_id']}",
                )
            ]
        )

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"admin_subs:{page - 1}"))
    if start + page_size < len(items):
        nav.append(InlineKeyboardButton("➡️", callback_data=f"admin_subs:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="admin_home")])
    return InlineKeyboardMarkup(rows)


def build_admin_user_keyboard(user_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🧾 Платежи пользователя", callback_data=f"admin_user_pay:{user_id}")],
            [InlineKeyboardButton("✏️ Редактировать дни", callback_data=f"admin_sub_edit:{user_id}")],
            [InlineKeyboardButton("🗑️ Удалить подписку", callback_data=f"admin_sub_remove:{user_id}")],
            [InlineKeyboardButton("⬅️ К подпискам", callback_data="admin_subs:0")],
        ]
    )


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
            text="Платеж отклонен. Если есть вопрос - напиши администратору.",
        )
        await update.message.reply_text("Готово. Платеж отклонен.")
    except Exception:
        await update.message.reply_text("Ошибка сети.")


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Недостаточно прав.")
        return
    await update.message.reply_text(
        "⚙️ Админ-панель\n"
        "Надежные команды:\n"
        "/subs - список активных подписок\n"
        "/sub_set <user_id> <days> - установить дни подписки\n"
        "/sub_del <user_id> - удалить подписку\n"
        "/pending - ожидающие платежи\n"
        "/payment <id> - детали платежа\n"
        "/user <user_id> - платежи пользователя",
        reply_markup=build_admin_menu(),
    )


async def subs_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Недостаточно прав.")
        return
    items = fetch_active_subscriptions()
    if not items:
        await update.message.reply_text("📅 Активных подписок не найдено.")
        return
    lines = ["📅 Активные подписки:", ""]
    for i, it in enumerate(items[:50], start=1):
        until = time.strftime("%Y-%m-%d", time.localtime(int(it["expires_at"])))
        lines.append(
            f"{i}. 👤 `{it['user_id']}`\n"
            f"   ⏳ Осталось: *{it['days_left']} дн*\n"
            f"   📆 До: *{until}*"
        )
    if len(items) > 50:
        lines.append("")
        lines.append(f"… и еще {len(items) - 50} пользователей")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def sub_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Недостаточно прав.")
        return
    raw_text = (update.message.text or "").strip()
    items, parse_errors = parse_sub_set_lines(raw_text)
    if not items and parse_errors:
        await update.message.reply_text("\n".join(parse_errors[:20]))
        return
    if not items:
        await update.message.reply_text(
            "Используй: /sub_set <user_id> <days>\n"
            "Или отправь несколько строк подряд с /sub_set."
        )
        return

    results: list[str] = []
    failed = 0

    for target_user, days in items:
        ok, message = set_subscription_days(target_user, days)
        results.append(("✅ " if ok else "❌ ") + message)
        if not ok:
            failed += 1

    if parse_errors:
        results.extend([f"❌ {msg}" for msg in parse_errors])
        failed += len(parse_errors)

    if len(items) == 1 and not parse_errors and results:
        await update.message.reply_text(results[0])
        return

    success = len(items) - (failed - len(parse_errors))
    await update.message.reply_text(
        f"Обработано: {len(items)}\n"
        f"Успешно: {success}\n"
        f"С ошибками: {failed}\n\n"
        + "\n".join(results[:80])
    )


async def sub_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Недостаточно прав.")
        return
    if not context.args:
        await update.message.reply_text("Используй: /sub_del <user_id>")
        return
    target_user = context.args[0].strip()
    try:
        r = requests.post(
            f"{SERVER_URL}/sub/remove",
            headers={"X-Bot-Secret": BOT_SECRET},
            json={"user_id": target_user},
            timeout=10,
        )
        if r.status_code != 200:
            await update.message.reply_text("Ошибка сервера при удалении подписки.")
            return
        data = r.json()
    except Exception:
        await update.message.reply_text("Ошибка сети.")
        return
    if data.get("removed"):
        await update.message.reply_text(
            f"✅ Подписка пользователя `{target_user}` удалена.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            f"ℹ️ У пользователя `{target_user}` нет активной подписки.",
            parse_mode="Markdown",
        )


def format_payment_line(p: dict) -> str:
    created = time.strftime("%Y-%m-%d", time.localtime(int(p.get("created_at", 0))))
    return (
        f"🧾 #{p.get('id')} | 👤 {p.get('user_id')} | "
        f"📦 {p.get('plan_months')}м | 💳 {p.get('method')} | "
        f"📌 {p.get('status')} | 📅 {created}"
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


async def setup_telegram_menu(application: Application) -> None:
    commands = [
        BotCommand("start", "Начать 🚀"),
        BotCommand("status", "Проверить подписку"),
        BotCommand("key_android", "Кей Android"),
        BotCommand("key_ios", "Кей iOS"),
    ]
    await application.bot.set_my_commands(commands)
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())


def main():
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")
    app = Application.builder().token(BOT_TOKEN).post_init(setup_telegram_menu).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("key", key))
    app.add_handler(CommandHandler("key_android", key_android))
    app.add_handler(CommandHandler("key_ios", key_ios))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("subs", subs_list))
    app.add_handler(CommandHandler("sub_set", sub_set))
    app.add_handler(CommandHandler("sub_del", sub_del))
    app.add_handler(CommandHandler("pending", pending))
    app.add_handler(CommandHandler("payment", payment))
    app.add_handler(CommandHandler("user", user_payments))
    app.add_handler(CommandHandler("ios_bind", ios_bind))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("reject", reject))
    app.add_handler(InlineQueryHandler(inline_query))
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
