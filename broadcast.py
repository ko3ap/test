"""
broadcast.py — шаблоны рассылок и логика отправки.
"""
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from config import SUPPORT_USERNAME

# ─── Шаблоны сообщений ───────────────────────────────────────────────────────

TEMPLATES = {
    "promo_speed": {
        "title": "⚡️ Интернет замедлился",
        "image": "/app/assets/promo_banner.jpg",
        "text": (
            "⚡️ <b>Заметили, что интернет стал работать медленнее?</b>\n\n"
            "На этой неделе ограничения усилились ещё сильнее!\n\n"
            "🤔 <b>Что делать?</b>\n"
            "Чтобы спокойно пользоваться Telegram, YouTube и мобильным "
            "интернетом без замедлений — подключите VPN прямо сейчас.\n\n"
            "⁉️ <b>Почему именно сейчас?</b>\n"
            "Сегодня действует скидка на доступ!\n"
            "Акция действует до <b>22:59 по МСК</b> 🔥\n\n"
            "👇 Нажимай кнопку ниже и верни себе тот интернет, который был раньше!"
        ),
        "button": ("🔑 Подключиться со скидкой", "buy"),
    },

    "last_chance": {
        "title": "⏰ Последний шанс",
        "image": "/app/assets/expiry_banner.jpg",
        "text": (
            "⏰ <b>Последний шанс, пока не заблокировали Telegram!</b>\n\n"
            "Не теряй доступ к свободному интернету!\n\n"
            "Продли VPN прямо сейчас, чтобы обходить глушилки "
            "и оставаться всегда на связи. Без VPN ты рискуешь потерять "
            "доступ к важным сервисам.\n\n"
            "🎯 <b>Действуй сейчас:</b> продли доступ и продолжай "
            "пользоваться быстрым VPN."
        ),
        "button": ("🔄 Продлить доступ", "buy"),
    },

    "trial_3h": {
        "title": "⏰ Пробный доступ заканчивается (3ч)",
        "image": "/app/assets/expiry_banner.jpg",
        "text": (
            "⏰ <b>Твой пробный доступ заканчивается через 3 часа!</b>\n\n"
            "Осталось совсем немного времени. Продли VPN прямо сейчас, "
            "чтобы не потерять доступ без перерывов.\n\n"
            "🎁 <b>Специальное предложение:</b>\n"
            "Продли доступ в течение 3 часов и получи бонусные дни! 🔥"
        ),
        "button": ("🔑 Продлить сейчас", "buy"),
    },

    "trial_1h": {
        "title": "🔥 Последний час пробного доступа",
        "image": "/app/assets/expiry_banner.jpg",
        "text": (
            "🔥 <b>Последний час пробного доступа!</b>\n\n"
            "VPN отключится через <b>1 час</b>. "
            "Продли прямо сейчас, чтобы не потерять связь.\n\n"
            "⚡️ Не упусти момент! Продолжай наслаждаться "
            "быстрым и безопасным интернетом."
        ),
        "button": ("🔑 Продлить сейчас", "buy"),
    },

    "referral": {
        "title": "👥 Реферальная программа",
        "image": "/app/assets/referral_banner.jpg",
        "text": (
            "🔥 <b>Пользуйся VPN бесплатно вместе с друзьями!</b>\n\n"
            "Хорошим нужно делиться — приглашай знакомых по своей ссылке "
            "и получай бонусы:\n\n"
            "👤 За приглашение друга — <b>+3 дня</b> доступа\n"
            "💰 Друг оплатил доступ — <b>+20% дней</b> от выбранного тарифа\n\n"
            "Приглашай сейчас — твоя ссылка находится во вкладке «👥 Друзья»"
        ),
        "button": ("👥 Мои друзья", "referral"),
    },

    "renewal_reminder": {
        "title": "💎 Понравился VPN?",
        "image": "/app/assets/welcome_banner.jpg",
        "text": (
            "💎 <b>Понравился VPN?</b>\n\n"
            "Ты уже попробовал наш сервис и оценил его качество. "
            "Продли доступ к VPN, чтобы обходить блокировки "
            "и оставаться всегда на связи!\n\n"
            "✨ <b>Что ты получишь:</b>\n"
            "• Стабильное соединение\n"
            "• Высокая скорость\n"
            "• Обход любых блокировок\n"
            "• Доступ ко всем серверам"
        ),
        "button": ("🔄 Продлить подписку", "buy"),
    },
}


def get_broadcast_keyboard(template_key: str) -> InlineKeyboardMarkup:
    tpl = TEMPLATES.get(template_key, {})
    btn_text, btn_action = tpl.get("button", ("🔑 Открыть бота", "buy"))
    rows = [[InlineKeyboardButton(text=btn_text, callback_data=btn_action)]]
    if btn_action != "buy":
        rows.append([InlineKeyboardButton(
            text=f"💬 Поддержка", url=f"https://t.me/{SUPPORT_USERNAME}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_broadcast(bot: Bot, user_ids: list[int], template_key: str) -> tuple[int, int]:
    """
    Отправить рассылку по списку user_ids.
    Возвращает (успешно, ошибок).
    """
    tpl = TEMPLATES[template_key]
    text = tpl["text"]
    image_path = tpl.get("image")
    kb = get_broadcast_keyboard(template_key)

    ok = 0
    fail = 0
    for uid in user_ids:
        try:
            if image_path:
                try:
                    await bot.send_photo(
                        uid,
                        FSInputFile(image_path),
                        caption=text,
                        parse_mode="HTML",
                        reply_markup=kb,
                    )
                except Exception:
                    await bot.send_message(uid, text, parse_mode="HTML", reply_markup=kb)
            else:
                await bot.send_message(uid, text, parse_mode="HTML", reply_markup=kb)
            ok += 1
        except Exception:
            fail += 1

    return ok, fail
