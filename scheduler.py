"""
scheduler.py — фоновые задачи:
  - каждые 12ч проверяем истёкшие / истекающие подписки
  - уведомляем пользователя и админа
  - автоматически отзываем истёкшие
"""
import asyncio
import logging
from datetime import datetime

from aiogram import Bot

import db
import vpn
from config import ADMIN_ID, SUPPORT_USERNAME

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 1 * 3600   # каждый час
WARN_DAYS = 3               # предупреждать за 3 дня


async def check_subscriptions(bot: Bot):
    # 1. Отзываем истёкшие подписки
    expired = db.get_expired_subscriptions()
    for sub in expired:
        tid = sub["telegram_id"]
        sub_id = sub["id"]
        conf_text = sub.get("conf_text")
        logger.info(f"Expiring subscription {sub_id} for user {tid}")
        db.expire_subscription(sub_id)
        # Отключаем пира в AmneziaWG
        if conf_text:
            vpn.disconnect_peer(conf_text)

        try:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔑 Купить новый ключ", callback_data="show_tariffs")
            ]])
            await bot.send_message(
                tid,
                "⏰ <b>Срок действия подписки истёк</b>\n\n"
                "Один из твоих VPN-ключей перестал работать.\n\n"
                "Купи новый ключ — подключение займёт меньше минуты 🚀",
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception as e:
            logger.warning(f"Cannot notify user {tid}: {e}")

        try:
            await bot.send_message(
                ADMIN_ID,
                f"❌ Подписка sub_id={sub_id} пользователя <code>{tid}</code> истекла. "
                f"Ключ возвращён в пул.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Cannot notify admin: {e}")

    # 2. Предупреждаем за 3 дня
    expiring_3d = db.get_expiring_subscriptions(WARN_DAYS)
    for sub in expiring_3d:
        tid = sub["telegram_id"]
        expires_at = sub.get("expires_at", "")
        try:
            exp_dt = datetime.fromisoformat(expires_at)
            days_left = max(0, (exp_dt - datetime.utcnow()).days)
        except Exception:
            days_left = "?"

        try:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔄 Продлить доступ", callback_data="show_tariffs")
            ]])
            await bot.send_message(
                tid,
                f"⏰ <b>Подписка истекает через {days_left} дн.</b>\n\n"
                f"Продли доступ заранее — и VPN продолжит работать без перерывов 🚀",
                parse_mode="HTML",
                reply_markup=kb,
            )
            db.mark_warned(sub["id"], "3d")
        except Exception as e:
            logger.warning(f"Cannot notify user {tid} (3d): {e}")

    # 3. Предупреждаем за 3 часа — срочно
    expiring_3h = db.get_expiring_subscriptions_hours(3)
    for sub in expiring_3h:
        tid = sub["telegram_id"]
        expires_at = sub.get("expires_at", "")
        try:
            exp_dt = datetime.fromisoformat(expires_at)
            mins_left = max(0, int((exp_dt - datetime.utcnow()).total_seconds() // 60))
            time_str = f"{mins_left // 60} ч {mins_left % 60} мин" if mins_left >= 60 else f"{mins_left} мин"
        except Exception:
            time_str = "скоро"

        try:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔑 Продлить сейчас", callback_data="show_tariffs")
            ]])
            await bot.send_message(
                tid,
                f"🚨 <b>Осталось {time_str} — подписка почти истекла!</b>\n\n"
                f"Продли прямо сейчас чтобы VPN не отключился 👇",
                parse_mode="HTML",
                reply_markup=kb,
            )
            db.mark_warned(sub["id"], "3h")
        except Exception as e:
            logger.warning(f"Cannot notify user {tid} (3h): {e}")

    # 4. Предупреждаем за 1 час — последний шанс
    expiring_1h = db.get_expiring_subscriptions_hours(1)
    for sub in expiring_1h:
        tid = sub["telegram_id"]
        expires_at = sub.get("expires_at", "")
        try:
            exp_dt = datetime.fromisoformat(expires_at)
            mins_left = max(0, int((exp_dt - datetime.utcnow()).total_seconds() // 60))
            time_str = f"{mins_left} мин"
        except Exception:
            time_str = "менее часа"

        try:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔑 Продлить сейчас", callback_data="show_tariffs")
            ]])
            await bot.send_message(
                tid,
                f"⚡ <b>До отключения осталось {time_str}!</b>\n\n"
                f"Продли подписку прямо сейчас — это займёт 30 секунд 👇",
                parse_mode="HTML",
                reply_markup=kb,
            )
            db.mark_warned(sub["id"], "1h")
        except Exception as e:
            logger.warning(f"Cannot notify user {tid} (1h): {e}")


async def scheduler_loop(bot: Bot):
    logger.info("Scheduler started")
    while True:
        try:
            await check_subscriptions(bot)
        except Exception as e:
            logger.exception(f"Scheduler error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)
