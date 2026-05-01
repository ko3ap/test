import uuid
import asyncio
import logging
from yookassa import Configuration, Payment
from config import YOKASSA_SHOP_ID, YOKASSA_SECRET_KEY

logger = logging.getLogger(__name__)

Configuration.account_id = YOKASSA_SHOP_ID
Configuration.secret_key = YOKASSA_SECRET_KEY


def create_payment(amount: float, description: str, label: str) -> tuple[str, str]:
    """
    Создать платёж в ЮКасса.
    Возвращает (payment_id, confirmation_url).
    """
    payment = Payment.create({
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": "https://t.me/baobabVPNN_bot"
        },
        "capture": True,
        "description": description,
        "metadata": {
            "label": label
        }
    }, uuid.uuid4())

    confirmation_url = payment.confirmation.confirmation_url
    return payment.id, confirmation_url


async def wait_for_payment(payment_id: str, timeout: int = 600, interval: int = 5) -> bool:
    """
    Ждать подтверждения платежа (polling).
    timeout — максимальное время ожидания в секундах (default 10 мин).
    interval — интервал проверки в секундах.
    Возвращает True если оплачен, False если истёк таймаут или отменён.
    """
    elapsed = 0
    while elapsed < timeout:
        await asyncio.sleep(interval)
        elapsed += interval
        try:
            payment = Payment.find_one(payment_id)
            if payment.status == "succeeded":
                return True
            if payment.status in ("canceled", "expired"):
                return False
        except Exception as e:
            logger.warning(f"Ошибка проверки платежа {payment_id}: {e}")
    return False
