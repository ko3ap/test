import random
import asyncio
import json
import os
from dotenv import load_dotenv
import aiohttp

load_dotenv("/root/VPN/.env")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL = "@bobvpn_info"
BOT_USERNAME = "baobabVPNN_bot"

MESSAGES = [
    "🕐 Интернет стал работать ещё хуже?\n\nПодключи VPN и пользуйся без ограничений!\n\n🚨 Сегодня скидка 63%\n⏳ До 22:59 по МСК\n\n👇 Жми кнопку и забирай доступ к стабильному интернету!",

    "😴 Вечерняя акция!\nБоб дарит скидку 62% на доступ к VPN и связи!\n\n🚨 Акция действует сегодня до 23:47 по МСК!\n\n👇 Нажми на кнопку ниже и успей воспользоваться скидкой, пока она действует!",

    "⚡️ Заметили, что интернет стал работать медленнее?\nНа этой неделе ограничения усилились ещё сильнее!\n\n🤔 Что делать?\nЧтобы спокойно пользоваться Telegram, YouTube и мобильным интернетом без замедлений — подключите VPN сейчас.\n\n⁉️ Почему именно сейчас?\nСегодня действует скидка на доступ! Акция действует до 22:59 по МСК🔥\n\n👇 Нажимай кнопку ниже и верни себе тот интернет, который был раньше!",

    "🔴🔴🔴🔴\n\n📣 До полной блокировки Telegram — осталось несколько часов!\n\nУже завтра его полностью заблокируют и доступ к перепискам потеряется насовсем!\n\n🔒 Подключи VPN и сохрани доступ к Telegram, интернету и остальным сервисам!\n\n🔥 Забирай доступ прямо сейчас со скидкой 63%\n⏳ Скидка действует только сегодня до 22:59 по МСК\n\n👇 Нажми кнопку ниже и забери доступ со скидкой, пока ещё есть время!",

    "🌐 YouTube тормозит? Telegram глючит?\n\nЭто не баг — это блокировки.\n\n✅ Подключи VPN от БОБа и забудь про ограничения!\n\n🔥 Скидка 63% — только сегодня до 22:59 МСК\n\n👇 Жми кнопку и возвращай нормальный интернет!",

    "🚀 Хватит терпеть медленный интернет!\n\nБОБ VPN — быстрый, стабильный, без логов.\n\n💰 Сегодня скидка 62% на все тарифы!\n⏳ Акция до 23:00 по МСК\n\n👇 Нажми и подключись прямо сейчас!",
]

async def send_promo():
    text = random.choice(MESSAGES)
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    keyboard = {
        "inline_keyboard": [[
            {"text": "🔥 Подключить VPN", "url": f"https://t.me/{BOT_USERNAME}?start=promo"}
        ]]
    }
    
    payload = {
        "chat_id": CHANNEL,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(keyboard)
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            result = await resp.json()
            if result.get("ok"):
                print(f"✅ Промо отправлено в {CHANNEL}")
            else:
                print(f"❌ Ошибка: {result}")

if __name__ == "__main__":
    asyncio.run(send_promo())
