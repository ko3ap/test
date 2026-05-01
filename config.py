"""Конфигурация бота. Секреты — только из переменных окружения."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Telegram (обязательно задать перед запуском бота)
TOKEN = os.environ.get("BOT_TOKEN", "").strip()

# ЮKassa (как в old_vpn/pay.py)
YOO_SHOP_ID = os.environ.get("YOO_SHOP_ID", "").strip()
YOO_SECRET_KEY = os.environ.get("YOO_SECRET_KEY", "").strip()

# Админ: числовой ID и username (команды /key, /ad, …)
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0") or 0)
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "ko3ap").strip().lstrip("@")

# Канал для проверки подписки (-100…)
NEWS_CHANNEL_ID = int(os.environ.get("NEWS_CHANNEL_ID", "-1002344853901"))
NEWS_CHANNEL_URL = os.environ.get(
    "NEWS_CHANNEL_URL",
    "https://t.me/ko3ap_vpn_news",
).strip()

# AmneziaWG — отключение пира при окончании подписки (как в egor/vpn.py)
VPN_DISCONNECT_ENABLED = os.environ.get("VPN_DISCONNECT_ENABLED", "1").lower() in (
    "1",
    "true",
    "yes",
)
AWG_CONTAINER = os.environ.get("AWG_CONTAINER", "amnezia-awg")
# В AmneziaWG интерфейс обычно awg0 (см. egor/.env.example); wg0 — запасной
AWG_INTERFACE = os.environ.get("AWG_INTERFACE", "awg0")
# На Windows Docker Desktop: npipe:////./pipe/docker_engine
DOCKER_BASE_URL = os.environ.get("DOCKER_BASE_URL", "").strip() or None

# Базы SQLite (файлы рядом с ботом или в data/)
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR)))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_USERS_PATH = str(DATA_DIR / os.environ.get("DB_USERS_FILE", "vpn_users.sql"))
DB_KEYS_PATH = str(DATA_DIR / os.environ.get("DB_KEYS_FILE", "vpn_keys.sql"))

# Ресурсы (можно скопировать из old_vpn или задать путь)
ASSETS_DIR = Path(os.environ.get("ASSETS_DIR", str(BASE_DIR / "assets")))
WELCOME_IMAGE = Path(os.environ.get("WELCOME_IMAGE", str(ASSETS_DIR / "main2.png")))
INSTRUCTION_VIDEO = Path(os.environ.get("INSTRUCTION_VIDEO", str(ASSETS_DIR / "tutVPN.mp4")))

# Фоновые задачи
DAILY_LOOP_SECONDS = int(os.environ.get("DAILY_LOOP_SECONDS", "3600"))
EXPIRED_CHECK_SECONDS = int(os.environ.get("EXPIRED_CHECK_SECONDS", "3600"))

# Опрос ЮKassa после создания платежа (секунды; макс. — пока платёж жив в ЮKassa)
PAYMENT_POLL_INTERVAL_SEC = int(os.environ.get("PAYMENT_POLL_INTERVAL_SEC", "5"))
PAYMENT_POLL_MAX_SECONDS = int(os.environ.get("PAYMENT_POLL_MAX_SECONDS", str(24 * 3600)))

# Файл «последний день декремента» (чтобы не списывать дважды в один день)
LAST_DECREMENT_FILE = DATA_DIR / "last_decrement.txt"
