"""
generate_images.py — генерация изображений для BOBVPN бота.
Запускать: python3 generate_images.py
Выходные файлы кладутся в папку assets/
"""
from PIL import Image, ImageDraw, ImageFont
import os

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
os.makedirs(ASSETS, exist_ok=True)

FONT_BOLD    = os.path.join(ASSETS, "Font-Bold.ttf")
FONT_REGULAR = os.path.join(ASSETS, "Font-Regular.ttf")

# ─── Цвета BOBVPN ─────────────────────────────────────────────────────────────
BG_DARK   = (11, 17, 32)       # тёмно-синий фон
BG_CARD   = (18, 27, 48)       # чуть светлее для карточек
ACCENT    = (0, 217, 165)      # мятно-зелёный акцент
ACCENT2   = (0, 140, 255)      # синий акцент
WHITE     = (255, 255, 255)
GREY      = (140, 155, 180)
RED       = (255, 75, 75)
YELLOW    = (255, 210, 0)
GREEN     = (0, 217, 130)


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REGULAR
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def gradient_bg(draw: ImageDraw.ImageDraw, w: int, h: int,
                top: tuple, bottom: tuple):
    """Вертикальный градиент фона."""
    for y in range(h):
        t = y / h
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))


def rounded_rect(draw: ImageDraw.ImageDraw, xy, radius: int, fill, outline=None, width=2):
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill,
                            outline=outline, width=width)


def text_center(draw: ImageDraw.ImageDraw, y: int, text: str,
                font, fill, img_w: int):
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    draw.text(((img_w - tw) // 2, y), text, font=font, fill=fill)


# ─── 1. Главный логотип / Welcome Banner ─────────────────────────────────────

def make_welcome_banner():
    W, H = 1100, 600
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    # Фон — градиент
    gradient_bg(draw, W, H, (8, 14, 28), (14, 22, 45))

    # Декоративные круги
    for cx, cy, r, alpha in [
        (150, 120, 220, 18),
        (W - 120, H - 100, 180, 15),
        (W // 2, H + 60, 300, 12),
    ]:
        for i in range(3):
            draw.ellipse(
                [cx - r + i*20, cy - r + i*20, cx + r - i*20, cy + r - i*20],
                outline=(*ACCENT, alpha - i*4), width=1
            )

    # Логотип — щит (текстовый)
    shield_font = load_font(100, bold=True)
    draw.text((W // 2 - 55, 60), "🛡", font=shield_font, fill=WHITE)

    # Название
    title_font = load_font(92, bold=True)
    text_center(draw, 175, "BOB VPN", title_font, WHITE, W)

    # Акцентная линия под названием
    lw = 280
    lx = (W - lw) // 2
    draw.rectangle([lx, 283, lx + lw, 287], fill=ACCENT)

    # Слоган
    slogan_font = load_font(32)
    text_center(draw, 305, "Свободный интернет без границ", slogan_font, GREY, W)

    # Фичи
    features = [
        ("👻", "Не определяется как VPN"),
        ("🌍", "Сервер в Германии"),
        ("⚡", "Протокол AmneziaWG"),
        ("🚫", "Без логов"),
    ]
    feat_font = load_font(26)
    cols = 2
    col_w = W // cols
    for i, (icon, text) in enumerate(features):
        col = i % cols
        row = i // cols
        x = col * col_w + 90
        y = 385 + row * 55
        # Иконка-бейдж
        rounded_rect(draw, [x - 8, y - 8, x + 38, y + 34], 10, BG_CARD)
        draw.text((x, y), icon, font=load_font(28), fill=WHITE)
        draw.text((x + 48, y + 3), text, font=feat_font, fill=GREY)

    # Нижняя плашка
    rounded_rect(draw, [lx - 40, 510, lx + lw + 40, 560], 16, ACCENT)
    cta_font = load_font(26, bold=True)
    text_center(draw, 523, "🔑  Нажми «Купить ключ» чтобы начать", cta_font, BG_DARK, W)

    out = os.path.join(ASSETS, "welcome_banner.jpg")
    img.save(out, "JPEG", quality=95)
    print(f"✅ welcome_banner.jpg")
    return out


# ─── 2. Баннер «Счёт на оплату» ──────────────────────────────────────────────

def make_payment_banner():
    W, H = 1000, 520
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    gradient_bg(draw, W, H, (8, 14, 28), (12, 20, 40))

    # Карточка
    rounded_rect(draw, [40, 30, W - 40, H - 30], 24, BG_CARD)

    # Заголовок
    title_font = load_font(52, bold=True)
    text_center(draw, 60, "💳  Счёт на оплату", title_font, WHITE, W)

    # Линия
    draw.rectangle([100, 130, W - 100, 133], fill=ACCENT)

    # Иконка
    icon_font = load_font(80)
    text_center(draw, 145, "🛡", icon_font, WHITE, W)

    # Текст
    lbl_font  = load_font(28)
    val_font  = load_font(30, bold=True)

    items = [
        ("📱 Устройств:",  "1 устройство"),
        ("🌍 Сервер:",     "Германия 🇩🇪"),
    ]
    for i, (lbl, val) in enumerate(items):
        y = 255 + i * 50
        draw.text((110, y), lbl,  font=lbl_font, fill=GREY)
        draw.text((390, y), val,  font=val_font, fill=WHITE)

    # Цена — большой акцент
    price_font = load_font(72, bold=True)
    text_center(draw, 355, "720 ₽", price_font, ACCENT, W)

    # Кнопка-заглушка
    rounded_rect(draw, [200, 445, W - 200, 495], 14, ACCENT)
    btn_font = load_font(26, bold=True)
    text_center(draw, 457, "Оплатить →", btn_font, BG_DARK, W)

    out = os.path.join(ASSETS, "payment_banner.jpg")
    img.save(out, "JPEG", quality=95)
    print(f"✅ payment_banner.jpg")
    return out


# ─── 3. Баннер «Подписка истекает» ───────────────────────────────────────────

def make_expiry_banner():
    W, H = 1000, 480
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    gradient_bg(draw, W, H, (25, 10, 10), (40, 15, 15))

    rounded_rect(draw, [40, 30, W - 40, H - 30], 24, (30, 14, 14))

    # Заголовок с иконкой
    title_font = load_font(52, bold=True)
    text_center(draw, 55, "⏰  Подписка заканчивается", title_font, RED, W)
    draw.rectangle([100, 123, W - 100, 126], fill=RED)

    # Большой таймер
    timer_font = load_font(100, bold=True)
    text_center(draw, 145, "3", timer_font, RED, W)
    sub_font = load_font(34)
    text_center(draw, 265, "дня до отключения", sub_font, GREY, W)

    # Текст
    body_font = load_font(27)
    text_center(draw, 320, "Продли доступ — и VPN продолжит работать", body_font, WHITE, W)
    text_center(draw, 365, "без перерывов на всех твоих устройствах", body_font, GREY, W)

    # Кнопка
    rounded_rect(draw, [200, 405, W - 200, 455], 14, RED)
    btn_font = load_font(26, bold=True)
    text_center(draw, 417, "🔄  Продлить подписку", btn_font, WHITE, W)

    out = os.path.join(ASSETS, "expiry_banner.jpg")
    img.save(out, "JPEG", quality=95)
    print(f"✅ expiry_banner.jpg")
    return out


# ─── 4. Баннер «Акция / Скидка» ──────────────────────────────────────────────

def make_promo_banner():
    W, H = 1000, 520
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    gradient_bg(draw, W, H, (12, 25, 14), (10, 20, 25))

    rounded_rect(draw, [40, 30, W - 40, H - 30], 24, (14, 30, 18))

    # Бейдж "АКЦИЯ"
    rounded_rect(draw, [(W - 200) // 2, 48, (W + 200) // 2, 95], 20, YELLOW)
    badge_font = load_font(26, bold=True)
    text_center(draw, 58, "🔥  АКЦИЯ  🔥", badge_font, BG_DARK, W)

    title_font = load_font(52, bold=True)
    text_center(draw, 110, "Интернет замедлился?", title_font, WHITE, W)
    draw.rectangle([100, 178, W - 100, 181], fill=GREEN)

    body_font = load_font(28)
    lines = [
        "На этой неделе ограничения усилились.",
        "VPN — единственный способ вернуть",
        "нормальный YouTube и Telegram.",
    ]
    for i, line in enumerate(lines):
        text_center(draw, 200 + i * 44, line, body_font, GREY, W)

    # Цена со скидкой
    old_font = load_font(34)
    new_font = load_font(72, bold=True)
    old_price_w = old_font.getbbox("340 ₽")[2]
    ox = (W - old_price_w) // 2
    draw.text((ox, 342), "340 ₽", font=old_font, fill=GREY)
    draw.line([(ox - 5, 360), (ox + old_price_w + 5, 360)], fill=RED, width=3)

    text_center(draw, 360, "170 ₽  за месяц", new_font, GREEN, W)

    # Дедлайн
    dl_font = load_font(24)
    text_center(draw, 448, "⏰ Акция действует до 22:59 МСК", dl_font, YELLOW, W)

    # Кнопка
    rounded_rect(draw, [200, 465, W - 200, 510], 14, GREEN)
    btn_font = load_font(26, bold=True)
    text_center(draw, 477, "🔑  Подключиться сейчас", btn_font, BG_DARK, W)

    out = os.path.join(ASSETS, "promo_banner.jpg")
    img.save(out, "JPEG", quality=95)
    print(f"✅ promo_banner.jpg")
    return out


# ─── 5. Баннер «Реферальная программа» ───────────────────────────────────────

def make_referral_banner():
    W, H = 1000, 500
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    gradient_bg(draw, W, H, (12, 18, 35), (18, 25, 50))

    rounded_rect(draw, [40, 30, W - 40, H - 30], 24, BG_CARD)

    title_font = load_font(50, bold=True)
    text_center(draw, 55, "👥  Пригласи друга", title_font, WHITE, W)
    draw.rectangle([100, 123, W - 100, 126], fill=ACCENT2)

    # Бонусы
    items = [
        ("👤", "+3 дня",  "за каждого приглашённого"),
        ("💰", "+20%",    "дней когда друг оплатит тариф"),
    ]
    for i, (icon, val, desc) in enumerate(items):
        bx = 90 + i * 460
        by = 155
        rounded_rect(draw, [bx, by, bx + 400, by + 190], 18, (22, 35, 65))

        icon_f = load_font(52)
        draw.text((bx + 20, by + 15), icon, font=icon_f, fill=WHITE)

        val_f = load_font(56, bold=True)
        draw.text((bx + 90, by + 15), val, font=val_f, fill=ACCENT)

        desc_f = load_font(24)
        # перенос строки
        words = desc.split()
        line = ""
        dy = by + 95
        for w in words:
            test = (line + " " + w).strip()
            if load_font(24).getbbox(test)[2] < 340:
                line = test
            else:
                draw.text((bx + 20, dy), line, font=desc_f, fill=GREY)
                dy += 34
                line = w
        if line:
            draw.text((bx + 20, dy), line, font=desc_f, fill=GREY)

    body_font = load_font(26)
    text_center(draw, 368, "Твоя реферальная ссылка находится в разделе", body_font, GREY, W)
    text_center(draw, 404, "«👥 Друзья» в главном меню бота", body_font, WHITE, W)

    # Кнопка
    rounded_rect(draw, [250, 430, W - 250, 475], 14, ACCENT2)
    btn_font = load_font(24, bold=True)
    text_center(draw, 442, "🔗  Поделиться ссылкой", btn_font, WHITE, W)

    out = os.path.join(ASSETS, "referral_banner.jpg")
    img.save(out, "JPEG", quality=95)
    print(f"✅ referral_banner.jpg")
    return out


if __name__ == "__main__":
    print("Генерирую изображения BOBVPN...")
    make_welcome_banner()
    make_payment_banner()
    make_expiry_banner()
    make_promo_banner()
    make_referral_banner()
    print("\n✅ Все изображения готовы в папке assets/")
