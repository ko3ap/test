# 🚀 DEPLOY.md — Перенос BOBVPN на новый сервер

## Требования

- VPS Ubuntu 22.04+ (минимум 1 CPU / 1GB RAM)
- Docker + Docker Compose v2
- SSH доступ
- Открытый UDP порт для AmneziaWG (38962 или свой)

---

## ⚠️ КЛЮЧЕВЫЕ МОМЕНТЫ ПРИ ПЕРЕНОСЕ

### 1. AmneziaWG — новый сервер = новые ключи = старые конфиги НЕ РАБОТАЮТ

При смене сервера меняется IP. Все `.conf` файлы в базе данных
привязаны к старому IP — пользователи не смогут подключиться.

**Что делать:**
- После установки AmneziaWG на новом сервере создай новые ключи в Amnezia Desktop
- Загрузи новые `.conf` файлы в бота через `/addkey`
- Активным пользователям нужно будет получить и переустановить новые ключи

### 2. Имя контейнера AmneziaWG

Бот управляет пирами через Docker socket. После запуска проверь:
```bash
docker ps --format "{{.Names}}"
```
Если имя контейнера отличается от `amnezia-awg` — добавь в `.env`:
```
AWG_CONTAINER=реальное_имя
```

### 3. Интерфейс WireGuard

Реальный интерфейс — `wg0` (дефолт уже верный). Проверить:
```bash
docker exec amnezia-awg ip link show | grep wg
```

### 4. config.py — обязательно поменяй

```python
ADMIN_ID = 861436816        # ← твой Telegram ID (@userinfobot)
SUPPORT_USERNAME = "..."    # ← юзернейм поддержки
NEWS_CHANNEL = "@bobvpn_info"  # ← канал подписки

YOKASSA_SHOP_ID = "..."     # ← ID магазина ЮКасса
YOKASSA_SECRET_KEY = "live_..."  # ← live ключ для прода / test_ для теста
```

### 5. База данных — перенеси если нужна история

```bash
# Старый сервер:
docker cp vpn-bot-vpn-bot-1:/app/data/bot.db ./bot.db

# Новый сервер (после первого запуска):
docker cp ./bot.db vpn-bot-vpn-bot-1:/app/data/bot.db
docker compose restart
```

> ⚠️ Перенесённые ключи в БД не будут работать — в них зашит старый IP.
> Пользователи с активными подписками получат новые ключи при следующем обращении.

---

## Шаг 1 — Установить Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

---

## Шаг 2 — Установить AmneziaWG

```bash
docker run -d \
  --name amnezia-awg \
  --cap-add NET_ADMIN \
  --cap-add SYS_MODULE \
  -p 38962:38962/udp \
  -v /opt/amnezia/awg:/etc/wireguard \
  --restart unless-stopped \
  amnezia/amneziawg
```

После запуска:
1. Открой **Amnezia Desktop** на своём компьютере
2. Подключись к новому серверу
3. Создай клиентов (каждый = один `.conf` файл для пула бота)

---

## Шаг 3 — Клонировать репо

```bash
git clone https://github.com/Frumzik/VPN.git
cd VPN
```

---

## Шаг 4 — Настроить .env

```bash
cp .env.example .env
nano .env
```

```env
BOT_TOKEN=токен_от_BotFather

# Если имя контейнера AWG отличается от amnezia-awg:
# AWG_CONTAINER=amnezia-awg

# Интерфейс (по умолчанию wg0 — менять не нужно):
# AWG_INTERFACE=wg0
```

---

## Шаг 5 — Обновить config.py

```bash
nano config.py
```

Поменяй `ADMIN_ID`, `SUPPORT_USERNAME`, `NEWS_CHANNEL`, `YOKASSA_SHOP_ID`, `YOKASSA_SECRET_KEY`.

---

## Шаг 6 — Запустить бота

```bash
docker compose up --build -d
docker logs vpn-bot-vpn-bot-1 -f
```

Ожидаемый вывод:
```
Starting bot...
Run polling for bot @твой_бот
```

---

## Шаг 7 — Загрузить ключи в бота

Отправь `.conf` файлы (из Amnezia Desktop) прямо в чат боту.

---

## 🔒 Безопасность сервера

### SSH — только по ключу

```bash
# Скопируй свой публичный ключ (с локальной машины):
ssh-copy-id user@new-server

# Отключи вход по паролю:
sudo nano /etc/ssh/sshd_config
# PasswordAuthentication no
# PermitRootLogin no
sudo systemctl restart sshd
```

### Firewall (UFW)

```bash
sudo apt install ufw -y
sudo ufw allow 22/tcp        # SSH
sudo ufw allow 38962/udp     # AmneziaWG
sudo ufw enable
sudo ufw status
```

### Fail2ban

```bash
sudo apt install fail2ban -y
sudo systemctl enable --now fail2ban
```

### Автообновления безопасности

```bash
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

---

## Как работает автоотключение пиров

При отзыве ключа (вручную или по истечении подписки) бот:
1. Добавляет `iptables DROP` правило для IP клиента — **мгновенный** разрыв соединения
2. Удаляет пира из WireGuard — **запрет** на повторное подключение

Это работает через Docker socket (монтируется в `docker-compose.yml`).

---

## Полезные команды

```bash
# Логи бота
docker logs vpn-bot-vpn-bot-1 -f

# Перезапуск
docker compose restart

# Обновление после git pull
git pull && docker compose up --build -d

# Все пиры в AWG
docker exec amnezia-awg wg show

# Подключиться к БД
docker exec vpn-bot-vpn-bot-1 python3 -c "import sqlite3; ..."
```

---

## Checklist перед запуском

- [ ] Docker установлен, демон стартует автоматически
- [ ] AmneziaWG запущен, пиры созданы в Amnezia Desktop
- [ ] Репо склонировано
- [ ] `.env` заполнен (BOT_TOKEN)
- [ ] `config.py` обновлён (ADMIN_ID, ЮКасса, канал)
- [ ] `docker compose up --build -d` выполнен
- [ ] Логи чистые — бот polling работает
- [ ] `.conf` файлы загружены в бота
- [ ] UFW включён, открыты только 22/tcp и 38962/udp
- [ ] Fail2ban работает
