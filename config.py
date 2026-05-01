import os

ADMIN_ID = 861436816
BOT_TOKEN = os.environ.get('7559500880:AAFIrWFH0KGmbKPFJmC1z5a4QpkLw7HGYhg')
DB_PATH = os.environ.get("DB_PATH", "/app/data/bot.db")
SUPPORT_USERNAME = "ko3ap"

# AmneziaWG — автоматическое отключение пиров при отзыве ключа
# Имя Docker-контейнера с AmneziaWG (см. docker ps)
AWG_CONTAINER = os.environ.get("AWG_CONTAINER", "amnezia-awg")
# Имя WireGuard-интерфейса внутри контейнера (обычно awg0)
AWG_INTERFACE  = os.environ.get("AWG_INTERFACE", "wg0")

# Новостной канал — пользователь должен быть подписан для использования бота
# Укажи @username или числовой ID канала (например -1001234567890)
NEWS_CHANNEL = "@bobvpn_info"

# ЮКасса
YOKASSA_SHOP_ID = '1032666'
YOKASSA_SECRET_KEY = 'test_NJ7FgoqJs1R-gYRUy3VSDs8Epx-_MdHLoe95pbUlVtY'

# Тарифы: key → {label, days, price}
TARIFFS = {
    "1m": {"label": "1 месяц",   "days": 30,  "price": 170},
    "3m": {"label": "3 месяца",  "days": 90,  "price": 450},
    "6m": {"label": "6 месяцев", "days": 180, "price": 720},
    "1y": {"label": "1 год",     "days": 365, "price": 1200},
}
