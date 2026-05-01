import asyncio
import logging
import os
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile, FSInputFile,
)

import db
import vpn
import payment as pay
from config import BOT_TOKEN, ADMIN_ID, TARIFFS, SUPPORT_USERNAME, NEWS_CHANNEL
from scheduler import scheduler_loop
from broadcast import TEMPLATES, send_broadcast

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

IMG_WELCOME  = "/app/assets/bob_welcome.jpg"
IMG_EXPIRY   = "/app/assets/expiry_banner.jpg"
IMG_PROMO    = "/app/assets/promo_banner.jpg"
IMG_REFERRAL = "/app/assets/referral_banner.jpg"


# ─── Keyboards ────────────────────────────────────────────────────────────────

def kb_main(user_id: int = 0) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="🔑 Купить ключ"),    KeyboardButton(text="👤 Личный кабинет")],
        [KeyboardButton(text="👥 Друзья"),            KeyboardButton(text="💬 Поддержка")],
    ]
    if user_id == ADMIN_ID:
        keyboard.append([KeyboardButton(text="⚙️ Админ")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def kb_tariffs() -> InlineKeyboardMarkup:
    base_price = TARIFFS["1m"]["price"]
    rows = []
    for key, t in TARIFFS.items():
        price = t["price"]
        if key == "6m":
            per_month = price / (t["days"] / 30)
            discount = round((1 - per_month / base_price) * 100)
            btn_text = f"⚡ {t['label']}  —  {price} ₽  (−{discount}%)"
        elif key == "1m":
            btn_text = f"{t['label']}  —  {price} ₽"
        else:
            per_month = price / (t["days"] / 30)
            discount = round((1 - per_month / base_price) * 100)
            btn_text = f"{t['label']}  —  {price} ₽  (−{discount}%)"
        rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"tariff_{key}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_cabinet(subs: list) -> InlineKeyboardMarkup:
    rows = []
    for i, s in enumerate(subs, 1):
        ip = vpn.get_ip_from_conf(s["conf_text"])
        dl = days_left_str(s.get("expires_at"))
        rows.append([InlineKeyboardButton(
            text=f"📥 Скачать ключ #{i}  ·  {ip}  ·  {dl}",
            callback_data=f"dl_sub_{s['id']}",
        )])
    rows.append([InlineKeyboardButton(text="❓ Я не знаю как использовать ключ", callback_data="how_to_use")])
    rows.append([InlineKeyboardButton(text="🛒 Купить ещё ключ",          callback_data="show_tariffs")])
    rows.append([InlineKeyboardButton(text=f"💬 Написать в поддержку",    url=f"https://t.me/{SUPPORT_USERNAME}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_no_subs() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Купить ключ", callback_data="show_tariffs")],
    ])


def kb_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика",     callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Пользователи",   callback_data="admin_users")],
        [InlineKeyboardButton(text="📥 Добавить ключ",  callback_data="admin_addkey")],
        [InlineKeyboardButton(text="🗑 Отозвать ключи", callback_data="admin_revoke_list")],
        [InlineKeyboardButton(text="📢 Рассылка",       callback_data="admin_broadcast")],
    ])


def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


# ─── Helpers ─────────────────────────────────────────────────────────────────

def days_left_str(expires_at: str | None) -> str:
    if not expires_at:
        return "♾️ бессрочно"
    try:
        exp = datetime.fromisoformat(expires_at)
        days = (exp - datetime.utcnow()).days
        if days < 0:  return "❌ истёк"
        if days == 0: return "⚠️ сегодня"
        if days == 1: return "⚠️ 1 день"
        if days <= 4: return f"⏳ {days} дня"
        return f"✅ {days} дн."
    except Exception:
        return "—"


def progress_bar(days_left: int, total_days: int, length: int = 10) -> str:
    if total_days <= 0:
        return "▓" * length
    filled = round(max(0, days_left) / total_days * length)
    return "▓" * filled + "░" * (length - filled)


async def send_photo_or_text(chat_id, image_path: str, caption: str,
                              reply_markup=None, parse_mode="HTML"):
    """Отправить фото с подписью, при ошибке — только текст."""
    try:
        await bot.send_photo(
            chat_id,
            FSInputFile(image_path),
            caption=caption,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )
    except Exception as e:
        logger.warning("send_photo failed (%s): %s — falling back to text", image_path, e)
        await bot.send_message(
            chat_id,
            caption,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )


# ─── Проверка подписки на канал ──────────────────────────────────────────────

async def is_subscribed(user_id: int) -> bool:
    """Проверить, подписан ли пользователь на новостной канал."""
    try:
        member = await bot.get_chat_member(NEWS_CHANNEL, user_id)
        return member.status not in ("left", "kicked", "restricted")
    except Exception:
        return True  # Если канал недоступен — не блокируем пользователя


def kb_subscribe() -> InlineKeyboardMarkup:
    channel = NEWS_CHANNEL if NEWS_CHANNEL.startswith("@") else f"https://t.me/c/{NEWS_CHANNEL}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=f"https://t.me/{NEWS_CHANNEL.lstrip('@')}")],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")],
    ])


# ─── /start ───────────────────────────────────────────────────────────────────

BONUS_JOIN_DAYS = 3    # бонус рефереру за регистрацию друга
BONUS_PAY_PCT   = 0.20 # бонус рефереру за первую оплату — 20% от дней тарифа


@dp.message(Command("start"))
async def cmd_start(message: Message):
    name = (message.from_user.first_name or "").strip() or "пользователь"
    user_id = message.from_user.id

    # Обработка реферальной ссылки
    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1][4:])
            if referrer_id != user_id and not db.get_referrer(user_id):
                is_new = db.set_referrer(user_id, referrer_id)
                if is_new:
                    # Бонус рефереру если есть активная подписка
                    added = db.add_bonus_days(referrer_id, BONUS_JOIN_DAYS)
                    if added:
                        try:
                            await bot.send_message(
                                referrer_id,
                                f"🎉 По твоей ссылке пришёл новый друг! Ты получил +{BONUS_JOIN_DAYS} дня к подписке 🚀",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass
        except (ValueError, TypeError):
            pass

    # Проверяем подписку на канал
    if not await is_subscribed(message.from_user.id):
        await send_photo_or_text(
            message.chat.id,
            IMG_WELCOME,
            f"👋 Привет, <b>{name}</b>!\n\n"
            f"Чтобы пользоваться <b>БОБ VPN</b>, подпишись на наш канал — "
            f"там новости, акции и обновления сервиса.\n\n"
            f"📢 {NEWS_CHANNEL}\n\n"
            f"После подписки нажми кнопку <b>✅ Я подписался</b> 👇",
            reply_markup=kb_subscribe(),
        )
        return

    subs = db.get_user_subscriptions(message.from_user.id)

    if subs:
        exp = subs[0].get("expires_at")
        dl = days_left_str(exp)
        count = len(subs)
        await send_photo_or_text(
            message.chat.id,
            IMG_WELCOME,
            f"👋 С возвращением, <b>{name}</b>!\n\n"
            f"Твой VPN работает. Всё под контролем 💪\n\n"
            f"🟢 Активных ключей: <b>{count}</b>\n"
            f"⏳ Действует ещё: <b>{dl}</b>",
            reply_markup=kb_main(message.from_user.id),
        )
    else:
        await send_photo_or_text(
            message.chat.id,
            IMG_WELCOME,
            f"👋 Привет, <b>{name}</b>!\n\n"
            "Добро пожаловать в <b>БОБ VPN</b> — твой личный доступ к свободному интернету.\n\n"
            "Нажми <b>🔑 Купить ключ</b> — подключение займёт 2 минуты 👇",
            reply_markup=kb_main(message.from_user.id),
        )


# ─── 🔑 Купить ключ ──────────────────────────────────────────────────────────

@dp.message(F.text == "🔑 Купить ключ")
async def btn_buy(message: Message):
    free = db.get_free_keys_count()
    if free == 0:
        await message.answer(
            "😔 <b>Свободных мест нет</b>\n\n"
            f"Напишите в поддержку — уведомим как появятся:\n@{SUPPORT_USERNAME}",
            parse_mode="HTML",
        )
        return
    await _show_tariffs(message.chat.id)


# ─── 👥 Друзья / Реферальная система ───────────────────────────────────────────────────

@dp.message(F.text == "👥 Друзья")
async def btn_referral(message: Message):
    user_id = message.from_user.id
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    stats = db.get_referral_stats(user_id)

    text = (
        f"👥 <b>Реферальная программа</b>\n\n"
        f"🔗 Твоя ссылка:\n<code>{ref_link}</code>\n\n"
        f"👤 Приглашено друзей: <b>{stats['total']}</b>\n"
        f"💰 Оплатили подписку: <b>{stats['paid']}</b>\n\n"
        f"🎁 <b>Награды:</b>\n"
        f"• +{BONUS_JOIN_DAYS} дня за приглашение друга\n"
        f"• +20% дней от тарифа друга за его первую оплату"
    )
    await bot.send_message(message.chat.id, text, parse_mode="HTML")


@dp.callback_query(F.data == "show_tariffs")
async def cb_show_tariffs(callback: CallbackQuery):
    await callback.answer()
    free = db.get_free_keys_count()
    if free == 0:
        await callback.message.answer(
            f"😔 Свободных мест нет. Напишите: @{SUPPORT_USERNAME}",
        )
        return
    await _show_tariffs(callback.message.chat.id)


async def _show_tariffs(chat_id: int):
    await bot.send_message(
        chat_id,
        "💡 <b>Выберите тариф</b>\n\n"
        "🆕 Подключение к BOBVPN\n"
        "📱 Устройств: 1 устройство\n"
        "🌍 Сервер: Германия 🇩🇪\n"
        "🚫 Без логов и слежки\n\n"
        "🔔 Нажмите на тариф ниже для оформления\n"
        "❗️ После оплаты ключ будет выдан автоматически",
        parse_mode="HTML",
        reply_markup=kb_tariffs(),
    )


@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(callback: CallbackQuery):
    """Пользователь нажал '✅ Я подписался' — перепроверяем."""
    if not await is_subscribed(callback.from_user.id):
        await callback.answer("❌ Ты ещё не подписан на канал!", show_alert=True)
        return
    await callback.answer("✅ Отлично!")
    await callback.message.delete()
    # Показываем нормальный /start
    name = (callback.from_user.first_name or "").strip() or "пользователь"
    subs = db.get_user_subscriptions(callback.from_user.id)
    if subs:
        exp = subs[0].get("expires_at")
        dl = days_left_str(exp)
        count = len(subs)
        await send_photo_or_text(
            callback.message.chat.id,
            IMG_WELCOME,
            f"👋 С возвращением, <b>{name}</b>!\n\n"
            f"Твой VPN работает. Всё под контролем 💪\n\n"
            f"🟢 Активных ключей: <b>{count}</b>\n"
            f"⏳ Действует ещё: <b>{dl}</b>",
            reply_markup=kb_main(callback.from_user.id),
        )
    else:
        await send_photo_or_text(
            callback.message.chat.id,
            IMG_WELCOME,
            f"👋 Привет, <b>{name}</b>!\n\n"
            "Добро пожаловать в <b>БОБ VPN</b> — твой личный доступ к свободному интернету.\n\n"
            "Нажми <b>🔑 Купить ключ</b> — подключение займёт 2 минуты 👇",
            reply_markup=kb_main(callback.from_user.id),
        )


@dp.callback_query(F.data == "back_to_start")
async def cb_back(callback: CallbackQuery):
    await callback.answer()
    await callback.message.delete()


# ─── Выбор тарифа → выдача ───────────────────────────────────────────────────

@dp.callback_query(F.data.startswith("tariff_"))
async def cb_tariff(callback: CallbackQuery):
    await callback.answer()
    tariff_key = callback.data.replace("tariff_", "")
    if tariff_key not in TARIFFS:
        return

    tariff = TARIFFS[tariff_key]
    telegram_id = callback.from_user.id

    # Проверяем наличие ключей
    free = db.get_free_keys_count()
    if free == 0:
        await callback.message.answer(
            f"😔 <b>Свободных ключей нет</b>\n\nНапишите: @{SUPPORT_USERNAME}",
            parse_mode="HTML",
        )
        return

    wait = await callback.message.answer("⏳ Создаём ссылку на оплату...")

    try:
        label = f"{telegram_id}_{tariff_key}_{int(datetime.utcnow().timestamp())}"
        payment_id, pay_url = pay.create_payment(
            amount=tariff["price"],
            description=f"БОБ VPN — {tariff['label']}",
            label=label,
        )
    except Exception as e:
        logger.error(f"Ошибка создания платежа: {e}")
        await wait.edit_text("❌ Ошибка создания платежа. Попробуйте позже.")
        return

    await wait.edit_text(
        f"💳 <b>Оплата {tariff['label']} — {tariff['price']} ₽</b>\n\n"
        f"Нажми кнопку ниже для оплаты.\n"
        f"Ключ будет выдан автоматически после подтверждения платежа ✅",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💳 Оплатить {tariff['price']} ₽", url=pay_url)],
        ]),
    )

    # Ждём оплату в фоне
    asyncio.create_task(_wait_and_issue_key(
        telegram_id=telegram_id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
        tariff_key=tariff_key,
        payment_id=payment_id,
    ))


async def _wait_and_issue_key(telegram_id: int, username: str, full_name: str,
                               tariff_key: str, payment_id: str):
    """Фоновая задача: ждём оплату и выдаём ключ."""
    paid = await pay.wait_for_payment(payment_id, timeout=600)
    if not paid:
        return  # Таймаут или отмена — молча выходим

    key = db.get_free_key()
    if not key:
        await bot.send_message(
            telegram_id,
            f"✅ Оплата прошла, но свободных ключей нет.\nНапишите: @{SUPPORT_USERNAME}",
        )
        return

    tariff = TARIFFS[tariff_key]
    expires_at = (datetime.utcnow() + timedelta(days=tariff["days"])).isoformat()
    db.upsert_user(telegram_id, username or "", full_name or "")
    sub_id = db.create_subscription(telegram_id, key["id"], tariff_key, expires_at)

    # Применяем накопленные бонусные дни (копилка)
    pending = db.pop_pending_bonus_days(telegram_id)
    if pending > 0:
        db.add_bonus_days(telegram_id, pending)
        try:
            await bot.send_message(
                telegram_id,
                f"🎉 Тебе начислено +{pending} бонусных дней за реферальную программу! ❤️",
                parse_mode="HTML",
            )
        except Exception:
            pass

    exp_str = datetime.fromisoformat(expires_at).strftime("%d.%m.%Y")
    ip = vpn.get_ip_from_conf(key["conf_text"])

    # Подтверждение
    await bot.send_message(
        telegram_id,
        f"✅ <b>Оплата подтверждена, подписка оформлена на {tariff['label']}!</b>",
        parse_mode="HTML",
    )

    # Ключ
    await bot.send_document(
        telegram_id,
        BufferedInputFile(key["conf_text"].encode(), filename="vpn_key.txt"),
        caption=f"🔑 <b>Ключ БОБ VPN</b>\n📅 Активен до: {exp_str}",
        parse_mode="HTML",
    )

    # Поздравление
    # Видео-инструкция с текстом
    instruction_text = (
        "📲 <b>Как подключиться к БОБ VPN:</b>\n\n"
        "1️⃣ Скачай приложение <b>Amnezia VPN</b>\n"
        "   (iOS, Android, Windows, macOS)\n\n"
        "2️⃣ Открой файл <code>vpn_key.txt</code> который прислал бот\n\n"
        "3️⃣ Нажми <b>«Подключить»</b> — готово 🚀\n\n"
        f"Если что-то не получается — пиши: @{SUPPORT_USERNAME}"
    )
    video_id = _get_instruction_video_id()
    if video_id:
        if video_id.startswith("note:"):
            await bot.send_video_note(telegram_id, video_note=video_id[5:])
            await bot.send_message(telegram_id, instruction_text, parse_mode="HTML")
        elif video_id.startswith("doc:"):
            await bot.send_document(telegram_id, document=video_id[4:], caption=instruction_text, parse_mode="HTML")
        else:
            await bot.send_video(telegram_id, video=video_id, caption=instruction_text, parse_mode="HTML")
    elif os.path.exists(INSTRUCTION_VIDEO_PATH):
        msg = await bot.send_video(
            telegram_id,
            video=FSInputFile(INSTRUCTION_VIDEO_PATH),
            caption=instruction_text,
            parse_mode="HTML",
        )
        if msg.video:
            _save_instruction_video_id(msg.video.file_id)
    else:
        await bot.send_message(telegram_id, instruction_text, parse_mode="HTML")

    # Бонус рефереру за первую оплату
    referrer_id = db.get_referrer(telegram_id)
    if referrer_id and not db.is_referral_paid(telegram_id):
        db.mark_referral_paid(telegram_id)
        bonus_days = max(1, round(tariff["days"] * BONUS_PAY_PCT))
        added = db.add_bonus_days(referrer_id, bonus_days)
        if added:
            try:
                await bot.send_message(
                    referrer_id,
                    f"💰 Твой друг оплатил подписку! Ты получил +{bonus_days} дней к своей подписке 🎉",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    # Уведомление админу
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🆕 <b>Новая подписка</b>\n\n"
            f"👤 @{username or 'N/A'} ({telegram_id})\n"
            f"📦 Тариф: {tariff['label']} · {tariff['price']} ₽\n"
            f"🌐 IP: {ip}\n"
            f"📅 До: {exp_str}\n"
            f"🔑 sub_id={sub_id}",
            parse_mode="HTML",
        )
    except Exception:
        pass


async def _issue_key_UNUSED(telegram_id: int, username: str, full_name: str,
                     message: Message, tariff_key: str = "1m"):
    """УСТАРЕЛО — используется _wait_and_issue_key через оплату ЮКасса"""
    tariff = TARIFFS[tariff_key]
    wait = await message.answer("⏳ Оформляем доступ...")

    key = db.get_free_key()
    if not key:
        await wait.edit_text(
            f"😔 <b>Свободных ключей нет</b>\n\nНапишите: @{SUPPORT_USERNAME}",
            parse_mode="HTML",
        )
        return

    expires_at = (datetime.utcnow() + timedelta(days=tariff["days"])).isoformat()

    db.upsert_user(telegram_id, username or "", full_name or "")
    sub_id = db.create_subscription(telegram_id, key["id"], tariff_key, expires_at)

    await wait.delete()

    exp_str = datetime.fromisoformat(expires_at).strftime("%d.%m.%Y")
    ip = vpn.get_ip_from_conf(key["conf_text"])

    # Подтверждение оплаты
    await message.answer(
        f"✅ <b>Оплата подтверждена, подписка оформлена на {tariff['label']}!</b>",
        parse_mode="HTML",
    )

    # Отправляем ключ как .txt файл
    await message.answer_document(
        BufferedInputFile(key["conf_text"].encode(), filename="vpn_key.txt"),
        caption=f"🔑 <b>Ключ БОБ VPN</b>\n📅 Активен до: {exp_str}",
        parse_mode="HTML",
    )

    # Поздравление
    await message.answer(
        "🎉 <b>Поздравляем с оформлением подписки!</b>",
        parse_mode="HTML",
    )

    # Видео-инструкция (если загружена)
    video_id = _get_instruction_video_id()
    if video_id:
        if video_id.startswith("note:"):
            await bot.send_video_note(message.chat.id, video_note=video_id[5:])
        elif video_id.startswith("doc:"):
            await bot.send_document(message.chat.id, document=video_id[4:])
        else:
            await bot.send_video(
                message.chat.id,
                video=video_id,
                caption=(
                    "📹 <b>Как добавить ключ в приложение:</b>\n\n"
                    "1️⃣ Скачай <b>AmneziaWG</b> или <b>Amnezia VPN</b>\n"
                    "2️⃣ Нажмите на файл который прислал бот после покупки\n"
                    "3️⃣ Импортируйте его в приложение\n"
                    "4️⃣ Примите всё что запрашивает приложение\n"
                    "5️⃣ Нажми <b>Подключиться</b> 🚀\n\n"
                    "❓ Вопросы → @trap_sharkk"
                ),
                parse_mode="HTML",
            )
    elif os.path.exists(INSTRUCTION_VIDEO_PATH):
        msg = await bot.send_video(
            message.chat.id,
            video=FSInputFile(INSTRUCTION_VIDEO_PATH),
            caption=(
                "📹 <b>Как добавить ключ в приложение:</b>\n\n"
                "1️⃣ Скачай <b>AmneziaWG</b> или <b>Amnezia VPN</b>\n"
                "2️⃣ Нажмите на файл который прислал бот после покупки\n"
                "3️⃣ Импортируйте его в приложение\n"
                "4️⃣ Примите всё что запрашивает приложение\n"
                "5️⃣ Нажми <b>Подключиться</b> 🚀\n\n"
                "❓ Вопросы → @trap_sharkk"
            ),
            parse_mode="HTML",
        )
        try:
            _save_instruction_video_id(msg.video.file_id)
        except Exception:
            pass

    try:
        await bot.send_message(
            ADMIN_ID,
            f"🆕 <b>Новая подписка</b>\n\n"
            f"👤 @{username or 'N/A'} ({telegram_id})\n"
            f"📦 Тариф: {tariff['label']} · {tariff['price']} ₽\n"
            f"🌐 IP: {ip}\n"
            f"📅 До: {exp_str}\n"
            f"🔑 sub_id={sub_id}",
            parse_mode="HTML",
        )
    except Exception:
        pass


# ─── ❓ Инструкция по использованию ключа ────────────────────────────────────

INSTRUCTION_VIDEO_PATH = os.path.join(os.path.dirname(__file__), "assets", "instruction.mp4")
# После загрузки видео через бота сюда сохраняется file_id для быстрой переотправки
INSTRUCTION_VIDEO_ID_PATH = os.path.join(os.path.dirname(__file__), "data", "instruction_video_id.txt")

def _get_instruction_video_id() -> str | None:
    try:
        with open(INSTRUCTION_VIDEO_ID_PATH, "r") as f:
            return f.read().strip() or None
    except Exception:
        return None

def _save_instruction_video_id(file_id: str):
    os.makedirs(os.path.dirname(INSTRUCTION_VIDEO_ID_PATH), exist_ok=True)
    with open(INSTRUCTION_VIDEO_ID_PATH, "w") as f:
        f.write(file_id)


# ─── ❓ Инструкция по использованию ключа ────────────────────────────────────

@dp.callback_query(F.data == "how_to_use")
async def cb_how_to_use(callback: CallbackQuery):
    await callback.answer()
    text = (
        "📖 <b>Как использовать ключ БОБ VPN</b>\n\n"
        "1️⃣ Скачай приложение <b>Amnezia VPN</b>\n"
        "   iOS · Android · Windows · macOS\n\n"
        "2️⃣ Открой файл <code>vpn_key.txt</code> через Amnezia\n"
        "   (или нажми «Поделиться» → выбери Amnezia)\n\n"
        "3️⃣ Нажми <b>«Подключить»</b> — готово 🚀\n\n"
        f"Если что-то пошло не так — пиши: @{SUPPORT_USERNAME}"
    )
    video_id = _get_instruction_video_id()
    if video_id:
        if video_id.startswith("note:"):
            await callback.message.answer_video_note(video_note=video_id[5:])
            await callback.message.answer(text, parse_mode="HTML")
        elif video_id.startswith("doc:"):
            await callback.message.answer_document(document=video_id[4:], caption=text, parse_mode="HTML")
        else:
            await callback.message.answer_video(video=video_id, caption=text, parse_mode="HTML")
    elif os.path.exists(INSTRUCTION_VIDEO_PATH):
        msg = await callback.message.answer_video(video=FSInputFile(INSTRUCTION_VIDEO_PATH), caption=text, parse_mode="HTML")
        try:
            _save_instruction_video_id(msg.video.file_id)
        except Exception:
            pass
    else:
        await callback.message.answer(text, parse_mode="HTML")


# ─── 👤 Личный кабинет ───────────────────────────────────────────────────────

@dp.message(F.text == "👤 Личный кабинет")
async def btn_cabinet(message: Message):
    await _show_cabinet(message.chat.id, message.from_user.id)


async def _show_cabinet(chat_id: int, telegram_id: int):
    subs = db.get_user_subscriptions(telegram_id)

    if not subs:
        await bot.send_message(
            chat_id,
            "❌ <b>Активных подписок нет</b>\n\n"
            "Приобретите ключ, чтобы начать пользоваться VPN.",
            parse_mode="HTML",
            reply_markup=kb_no_subs(),
        )
        return

    lines = ["👤 <b>Личный кабинет</b>"]

    for i, s in enumerate(subs, 1):
        ip = vpn.get_ip_from_conf(s["conf_text"])
        tariff = TARIFFS.get(s.get("tariff_key", "1m"), {})
        assigned = (s.get("assigned_at") or "")[:10]
        try:
            assigned_fmt = datetime.fromisoformat(assigned).strftime("%d.%m.%Y")
        except Exception:
            assigned_fmt = assigned

        expires = s.get("expires_at")
        exp_fmt  = datetime.fromisoformat(expires).strftime("%d.%m.%Y") if expires else "Бессрочно"
        dl       = days_left_str(expires)

        lines.append(
            f"\n🔑 <b>Ключ #{i}</b>\n"
            f"📅 Период: {tariff.get('label', '—')}\n"
            f"🌍 Сервер: Германия 🇩🇪  ·  <code>{ip}</code>\n"
            f"📅 Подключён: {assigned_fmt}\n"
            f"📅 Истекает: {exp_fmt}\n"
            f"⏳ Осталось: {dl}"
        )

    lines.append(f"\n📦 Активных ключей: <b>{len(subs)}</b>")

    await bot.send_message(
        chat_id,
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=kb_cabinet(subs),
    )


@dp.callback_query(F.data.startswith("dl_sub_"))
async def cb_download_sub(callback: CallbackQuery):
    await callback.answer("Отправляю файл...")
    try:
        sub_id = int(callback.data.replace("dl_sub_", ""))
    except ValueError:
        return

    sub = db.get_subscription_by_id(sub_id)
    if not sub or sub["telegram_id"] != callback.from_user.id:
        await callback.message.answer("❌ Ключ не найден.")
        return

    all_subs = db.get_user_subscriptions(callback.from_user.id)
    idx = next((i + 1 for i, s in enumerate(all_subs) if s["id"] == sub_id), 1)

    await callback.message.answer_document(
        BufferedInputFile(sub["conf_text"].encode(), filename=f"bobvpn_{idx}.txt"),
        caption=f"🔑 <b>Ключ #{idx}</b> — открой через Amnezia VPN",
        parse_mode="HTML",
    )


# ─── 💬 Поддержка ─────────────────────────────────────────────────────────────

@dp.message(F.text == "💬 Поддержка")
async def btn_support(message: Message):
    await message.answer(
        "💬 <b>Поддержка BOBVPN</b>\n\n"
        f"По всем вопросам обращайтесь:\n@{SUPPORT_USERNAME}\n\n"
        "Мы отвечаем в течение нескольких часов.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"✉️ Написать @{SUPPORT_USERNAME}",
                                 url=f"https://t.me/{SUPPORT_USERNAME}")
        ]]),
    )


# ─── ⚙️ Панель администратора ─────────────────────────────────────────────────

@dp.message(Command("admin"))
@dp.message(F.text == "⚙️ Админ")
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await _send_admin_main(message)


async def _send_admin_main(message: Message, edit: bool = False):
    stats = db.get_stats()
    text = (
        f"⚙️ <b>Панель администратора</b>\n\n"
        f"🟢 Свободных ключей: <b>{stats['free']}</b>\n"
        f"🔴 Занятых: <b>{stats['used']}</b>\n"
        f"📦 Всего в пуле: <b>{stats['total']}</b>\n"
        f"👥 Пользователей: <b>{stats['users']}</b>\n"
        f"🔑 Активных подписок: <b>{stats['subs']}</b>"
    )
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=kb_admin())
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=kb_admin())


@dp.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    await _send_admin_main(callback.message, edit=True)


@dp.callback_query(F.data == "admin_users")
async def cb_admin_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    users = db.get_all_active_users_with_subs()

    if not users:
        await callback.message.edit_text(
            "Нет активных пользователей.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")
            ]]),
        )
        return

    lines = ["👥 <b>Активные пользователи:</b>\n"]
    for u in users:
        uname = f"@{u['username']}" if u.get("username") else f"id:{u['telegram_id']}"
        exp   = (u.get("earliest_exp") or "∞")[:10]
        count = u["sub_count"]
        dl    = days_left_str(u.get("earliest_exp"))
        lines.append(f"• {uname}  —  {count} 🔑  ·  {dl}  ·  до {exp}")

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")
        ]]),
    )


@dp.callback_query(F.data == "admin_addkey")
async def cb_admin_addkey(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    free = db.get_free_keys_count()
    await callback.message.edit_text(
        f"📥 <b>Добавить ключ в пул</b>\n\n"
        f"Свободных ключей: <b>{free}</b>\n\n"
        "Как добавить:\n"
        "1. Открой Amnezia Desktop\n"
        "2. Создай нового клиента\n"
        "3. «Поделиться» → сохрани как <code>.conf</code>\n"
        "4. Перешли файл сюда 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")
        ]]),
    )


@dp.callback_query(F.data == "admin_revoke_list")
async def cb_admin_revoke_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    users = db.get_all_active_users_with_subs()

    if not users:
        await callback.message.edit_text(
            "Нет активных пользователей.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")
            ]]),
        )
        return

    rows = []
    for u in users:
        uname = f"@{u['username']}" if u.get("username") else f"id:{u['telegram_id']}"
        rows.append([InlineKeyboardButton(
            text=f"🗑 {uname}  ({u['sub_count']} 🔑)",
            callback_data=f"admin_revoke_user_{u['telegram_id']}",
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])

    await callback.message.edit_text(
        "🗑 <b>Выберите пользователя:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@dp.callback_query(F.data.startswith("admin_revoke_user_"))
async def cb_admin_revoke_user(callback: CallbackQuery):
    """Показываем меню выбора: отозвать конкретный ключ или все сразу."""
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    try:
        tid = int(callback.data.replace("admin_revoke_user_", ""))
    except ValueError:
        return

    subs = db.get_user_subscriptions(tid)
    if not subs:
        await callback.message.edit_text(
            f"❌ Пользователь {tid} не найден или нет активных ключей.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="◀️ Назад", callback_data="admin_revoke_list")
            ]]),
        )
        return

    rows = []
    for i, s in enumerate(subs, 1):
        ip = vpn.get_ip_from_conf(s["conf_text"])
        exp = (s.get("expires_at") or "")[:10]
        rows.append([InlineKeyboardButton(
            text=f"🗑 Ключ #{i}  ·  {ip}  ·  до {exp}",
            callback_data=f"admin_revoke_sub_{s['id']}_{tid}",
        )])

    rows.append([InlineKeyboardButton(
        text=f"💥 Отозвать ВСЕ ключи ({len(subs)} шт.)",
        callback_data=f"admin_revoke_all_{tid}",
    )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_revoke_list")])

    await callback.message.edit_text(
        f"🗑 <b>Пользователь {tid}</b> — {len(subs)} активных ключей\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def _notify_user_revoked(tid: int):
    try:
        await bot.send_message(
            tid,
            f"❌ <b>Твой VPN-ключ был отозван</b>\n\n"
            f"Доступ к БОБ VPN прекращён. Если у тебя вопросы — напиши в поддержку: @{SUPPORT_USERNAME}",
            parse_mode="HTML",
        )
    except Exception:
        pass


@dp.callback_query(F.data.startswith("admin_revoke_sub_"))
async def cb_admin_revoke_sub(callback: CallbackQuery):
    """Отозвать один конкретный ключ."""
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    try:
        parts = callback.data.replace("admin_revoke_sub_", "").split("_")
        sub_id = int(parts[0])
        tid    = int(parts[1])
    except (ValueError, IndexError):
        return

    # Получаем conf ДО удаления, чтобы отключить пира в AWG
    conf_text = db.get_conf_text_by_sub(sub_id)
    ok = db.revoke_subscription(sub_id)
    if ok:
        if conf_text:
            vpn.disconnect_peer(conf_text)
        remaining = db.get_user_subscriptions(tid)
        await callback.message.edit_text(
            f"✅ Ключ отозван.\n\n"
            f"У пользователя <code>{tid}</code> осталось активных ключей: <b>{len(remaining)}</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ К пользователю",
                                      callback_data=f"admin_revoke_user_{tid}")],
                [InlineKeyboardButton(text="◀️ В панель", callback_data="admin_back")],
            ]),
        )
        await _notify_user_revoked(tid)
    else:
        await callback.message.edit_text(
            "❌ Ключ не найден.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="◀️ Назад", callback_data="admin_revoke_list")
            ]]),
        )


@dp.callback_query(F.data.startswith("admin_revoke_all_"))
async def cb_admin_revoke_all(callback: CallbackQuery):
    """Отозвать все ключи пользователя."""
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    try:
        tid = int(callback.data.replace("admin_revoke_all_", ""))
    except ValueError:
        return

    # Собираем conf до удаления, чтобы отключить пиров в AWG
    subs_before = db.get_user_subscriptions(tid)
    confs = [s["conf_text"] for s in subs_before if s.get("conf_text")]
    count = db.revoke_user_all(tid)
    for conf in confs:
        vpn.disconnect_peer(conf)
    if count:
        await callback.message.edit_text(
            f"✅ Отозвано <b>{count}</b> ключей пользователя <code>{tid}</code>.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")
            ]]),
        )
        await _notify_user_revoked(tid)
    else:
        await callback.message.edit_text(
            f"❌ Пользователь {tid} не найден.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")
            ]]),
        )


@dp.callback_query(F.data == "admin_back")
async def cb_admin_back(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    await _send_admin_main(callback.message, edit=True)


# ─── 📢 Рассылка ──────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    stats = db.get_stats()

    rows = []
    for key, tpl in TEMPLATES.items():
        rows.append([InlineKeyboardButton(
            text=tpl["title"],
            callback_data=f"broadcast_preview_{key}",
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])

    await callback.message.edit_text(
        f"📢 <b>Рассылка</b>\n\n"
        f"Получателей: <b>{stats['users']}</b> активных пользователей\n\n"
        f"Выберите шаблон:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@dp.callback_query(F.data.startswith("broadcast_preview_"))
async def cb_broadcast_preview(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    key = callback.data.replace("broadcast_preview_", "")
    tpl = TEMPLATES.get(key)
    if not tpl:
        return

    stats = db.get_stats()
    preview = tpl["text"][:600] + ("..." if len(tpl["text"]) > 600 else "")

    await callback.message.edit_text(
        f"📢 <b>Предпросмотр</b>\n\n"
        f"📌 {tpl['title']}\n"
        f"👥 Получателей: <b>{stats['users']}</b>\n\n"
        f"{preview}\n\n"
        f"⚠️ Рассылка уйдёт всем активным пользователям.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Отправить всем", callback_data=f"broadcast_send_{key}")],
            [InlineKeyboardButton(text="◀️ Назад",          callback_data="admin_broadcast")],
        ]),
    )


@dp.callback_query(F.data.startswith("broadcast_send_"))
async def cb_broadcast_send(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer("Отправляю...")
    key = callback.data.replace("broadcast_send_", "")
    if key not in TEMPLATES:
        return

    users    = db.get_all_active_users()
    user_ids = list({u["telegram_id"] for u in users})

    await callback.message.edit_text(
        f"⏳ Отправляю на <b>{len(user_ids)}</b> пользователей...",
        parse_mode="HTML",
    )

    ok, fail = await send_broadcast(bot, user_ids, key)

    await callback.message.edit_text(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"📤 Доставлено: <b>{ok}</b>\n"
        f"❌ Ошибок: <b>{fail}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ В панель", callback_data="admin_back")
        ]]),
    )


# ─── Приём файлов (admin) ─────────────────────────────────────────────────────

@dp.message(F.video)
async def handle_video(message: Message):
    """Админ загружает видео-инструкцию (сжатое видео)."""
    if not is_admin(message.from_user.id):
        return
    file_id = message.video.file_id
    _save_instruction_video_id(file_id)
    await message.answer(
        "✅ <b>Видео-инструкция сохранена!</b>\n\n"
        "Теперь при нажатии «❓ Я не знаю как использовать ключ» "
        "пользователи будут получать это видео.",
        parse_mode="HTML",
    )


@dp.message(F.video_note)
async def handle_video_note(message: Message):
    """Админ загружает видео-кружок как инструкцию."""
    if not is_admin(message.from_user.id):
        return
    file_id = message.video_note.file_id
    # Сохраняем с пометкой типа
    _save_instruction_video_id("note:" + file_id)
    await message.answer(
        "✅ <b>Видео-инструкция (кружок) сохранена!</b>",
        parse_mode="HTML",
    )


@dp.message(F.document)
async def handle_document(message: Message):
    if not is_admin(message.from_user.id):
        return
    doc = message.document
    mime = (doc.mime_type or "").lower()
    fname = (doc.file_name or "").lower()

    # Видео-файл без сжатия (отправлен как документ)
    if "video" in mime or fname.endswith((".mp4", ".mov", ".avi", ".mkv")):
        _save_instruction_video_id("doc:" + doc.file_id)
        await message.answer(
            "✅ <b>Видео-инструкция сохранена!</b>\n\n"
            "Теперь при нажатии «❓ Я не знаю как использовать ключ» "
            "пользователи будут получать это видео.",
            parse_mode="HTML",
        )
        return

    if not fname.endswith(".conf") and "text" not in mime:
        await message.answer("⚠️ Пришли .conf файл.")
        return

    file    = await bot.get_file(doc.file_id)
    content = await bot.download_file(file.file_path)
    conf    = content.read().decode("utf-8", errors="ignore").strip()

    if "[Interface]" not in conf or "[Peer]" not in conf:
        await message.answer("❌ Файл не похож на WireGuard конфиг.")
        return

    db.add_key_to_pool(conf)
    free = db.get_free_keys_count()
    await message.answer(
        f"✅ <b>Ключ добавлен в пул</b>\n\n"
        f"📦 Свободных ключей: <b>{free}</b>",
        parse_mode="HTML",
    )


# ─── Команды-алиасы ───────────────────────────────────────────────────────────

@dp.message(Command("mystatus"))
async def cmd_mystatus(message: Message):
    await btn_cabinet(message)



@dp.message(Command("revoke"))
async def cmd_revoke(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /revoke <telegram_id>")
        return
    try:
        tid = int(parts[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return

    count = db.revoke_user_all(tid)
    if count:
        await message.answer(f"✅ Отозвано {count} подписок у пользователя {tid}.")
        try:
            await bot.send_message(
                tid,
                f"❌ <b>Твой VPN-ключ был отозван</b>\n\n"
                f"Доступ к БОБ VPN прекращён. Если у тебя вопросы — напиши в поддержку: @{SUPPORT_USERNAME}",
                parse_mode="HTML",
            )
        except Exception:
            pass
    else:
        await message.answer(f"❌ Пользователь {tid} не найден.")


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    db.init_db()
    logger.info("Database initialized")
    asyncio.create_task(scheduler_loop(bot))
    logger.info("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
