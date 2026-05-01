import sqlite3
import os
import logging
from datetime import datetime

from config import DB_PATH

logger = logging.getLogger(__name__)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS key_pool (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                conf_text   TEXT    NOT NULL,
                added_at    TEXT    NOT NULL,
                is_used     INTEGER NOT NULL DEFAULT 0,
                used_by_telegram_id INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username    TEXT,
                full_name   TEXT,
                registered_at TEXT NOT NULL,
                -- legacy columns (kept for compat, не используются в новой логике)
                key_pool_id INTEGER REFERENCES key_pool(id),
                assigned_at TEXT,
                expires_at  TEXT,
                is_active   INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                key_pool_id INTEGER NOT NULL REFERENCES key_pool(id),
                tariff_key  TEXT    NOT NULL DEFAULT '1m',
                assigned_at TEXT    NOT NULL,
                expires_at  TEXT,
                is_active   INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_subs_user
            ON subscriptions(telegram_id, is_active)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id   INTEGER NOT NULL,
                referred_id   INTEGER NOT NULL UNIQUE,
                joined_at     TEXT NOT NULL,
                paid          INTEGER NOT NULL DEFAULT 0,
                bonus_days_given INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()
        _migrate(conn)
    logger.info("Database initialized")


# ─── referrals ──────────────────────────────────────────────────────────────

def set_referrer(referred_id: int, referrer_id: int) -> bool:
    """Записать реферала. Возвращает True если записан впервые."""
    now = datetime.utcnow().isoformat()
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO referrals (referrer_id, referred_id, joined_at) VALUES (?, ?, ?)",
                (referrer_id, referred_id, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id FROM referrals WHERE referred_id=? AND referrer_id=?",
                (referred_id, referrer_id),
            ).fetchone()
            return row is not None
    except Exception:
        return False


def get_referrer(referred_id: int) -> int | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT referrer_id FROM referrals WHERE referred_id=?", (referred_id,)
        ).fetchone()
        return row["referrer_id"] if row else None


def mark_referral_paid(referred_id: int):
    """Отметить что реферал совершил первую оплату."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE referrals SET paid=1 WHERE referred_id=? AND paid=0",
            (referred_id,),
        )
        conn.commit()


def is_referral_paid(referred_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT paid FROM referrals WHERE referred_id=?", (referred_id,)
        ).fetchone()
        return bool(row["paid"]) if row else False


def get_referral_stats(referrer_id: int) -> dict:
    """Статистика рефералов: всего приглашено, оплатили."""
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (referrer_id,)
        ).fetchone()[0]
        paid = conn.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND paid=1", (referrer_id,)
        ).fetchone()[0]
        return {"total": total, "paid": paid}


def add_bonus_days(telegram_id: int, days: int) -> int:
    """
    Продлить все активные подписки пользователя.
    Если подписок нет — положить в копилку pending_bonus_days.
    Возвращает кол-во продлённых подписок (0 = ушло в копилку).
    """
    from datetime import timedelta
    with get_conn() as conn:
        subs = conn.execute(
            "SELECT id, expires_at FROM subscriptions WHERE telegram_id=? AND is_active=1",
            (telegram_id,),
        ).fetchall()
        if subs:
            for sub in subs:
                try:
                    exp = datetime.fromisoformat(sub["expires_at"])
                except Exception:
                    exp = datetime.utcnow()
                new_exp = (exp + timedelta(days=days)).isoformat()
                conn.execute(
                    "UPDATE subscriptions SET expires_at=? WHERE id=?",
                    (new_exp, sub["id"]),
                )
            conn.commit()
            return len(subs)
        else:
            # Нет подписки — кладём в копилку
            conn.execute(
                "UPDATE users SET pending_bonus_days = pending_bonus_days + ? WHERE telegram_id=?",
                (days, telegram_id),
            )
            conn.commit()
            return 0


def pop_pending_bonus_days(telegram_id: int) -> int:
    """Забрать накопленные бонусные дни и обнулить копилку. Возвращает кол-во дней."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT pending_bonus_days FROM users WHERE telegram_id=?", (telegram_id,)
        ).fetchone()
        days = row["pending_bonus_days"] if row else 0
        if days > 0:
            conn.execute(
                "UPDATE users SET pending_bonus_days=0 WHERE telegram_id=?", (telegram_id,)
            )
            conn.commit()
        return days


def _migrate(conn):
    """Применяем миграции безопасно (идемпотентно)."""
    # Колонки subscriptions — флаги уведомлений
    sub_cols = {row[1] for row in conn.execute("PRAGMA table_info(subscriptions)").fetchall()}
    for col, sql in [
        ("warned_3d", "ALTER TABLE subscriptions ADD COLUMN warned_3d INTEGER NOT NULL DEFAULT 0"),
        ("warned_3h", "ALTER TABLE subscriptions ADD COLUMN warned_3h INTEGER NOT NULL DEFAULT 0"),
        ("warned_1h", "ALTER TABLE subscriptions ADD COLUMN warned_1h INTEGER NOT NULL DEFAULT 0"),
    ]:
        if col not in sub_cols:
            try:
                conn.execute(sql)
                logger.info(f"Migration: added column subscriptions.{col}")
            except Exception as e:
                logger.warning(f"Migration skipped ({col}): {e}")

    # Старые колонки users (для совместимости)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "pending_bonus_days" not in cols:
        try:
            conn.execute("ALTER TABLE users ADD COLUMN pending_bonus_days INTEGER NOT NULL DEFAULT 0")
            logger.info("Migration: added column users.pending_bonus_days")
        except Exception as e:
            logger.warning(f"Migration skipped (pending_bonus_days): {e}")
    legacy_cols = [
        ("is_active",   "ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"),
        ("full_name",   "ALTER TABLE users ADD COLUMN full_name TEXT"),
        ("key_pool_id", "ALTER TABLE users ADD COLUMN key_pool_id INTEGER REFERENCES key_pool(id)"),
        ("assigned_at", "ALTER TABLE users ADD COLUMN assigned_at TEXT"),
        ("expires_at",  "ALTER TABLE users ADD COLUMN expires_at TEXT"),
        ("registered_at","ALTER TABLE users ADD COLUMN registered_at TEXT"),
    ]
    for col, sql in legacy_cols:
        if col not in cols:
            try:
                conn.execute(sql)
                logger.info(f"Migration: added column users.{col}")
            except Exception as e:
                logger.warning(f"Migration skipped ({col}): {e}")

    # Миграция старых users → subscriptions (идемпотентно)
    old_users = conn.execute(
        "SELECT telegram_id, key_pool_id, assigned_at, expires_at "
        "FROM users WHERE key_pool_id IS NOT NULL AND is_active = 1"
    ).fetchall()
    for row in old_users:
        tid, kp_id, ass_at, exp_at = row
        exists = conn.execute(
            "SELECT id FROM subscriptions WHERE telegram_id=? AND key_pool_id=?",
            (tid, kp_id),
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO subscriptions (telegram_id, key_pool_id, tariff_key, assigned_at, expires_at, is_active) "
                "VALUES (?, ?, '1m', ?, ?, 1)",
                (tid, kp_id, ass_at or datetime.utcnow().isoformat(), exp_at),
            )
            logger.info(f"Migration: moved user {tid} key {kp_id} to subscriptions")
    conn.commit()


# ─── key_pool ────────────────────────────────────────────────────────────────

def add_key_to_pool(conf_text: str) -> int:
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO key_pool (conf_text, added_at, is_used) VALUES (?, ?, 0)",
            (conf_text, now),
        )
        conn.commit()
        return cur.lastrowid


def get_free_key():
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM key_pool WHERE is_used = 0 ORDER BY id LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def get_free_keys_count() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM key_pool WHERE is_used=0").fetchone()[0]


def release_key(key_id: int):
    """Устаревшая функция — ключи теперь удаляются, а не возвращаются в пул."""
    delete_key(key_id)


def delete_key(key_id: int):
    """Полностью удалить ключ из пула (повторная выдача невозможна)."""
    with get_conn() as conn:
        conn.execute("UPDATE users SET key_pool_id=NULL WHERE key_pool_id=?", (key_id,))
        conn.execute("DELETE FROM key_pool WHERE id=?", (key_id,))
        conn.commit()


def get_key_by_id(key_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM key_pool WHERE id=?", (key_id,)).fetchone()
        return dict(row) if row else None


# ─── users ───────────────────────────────────────────────────────────────────

def upsert_user(telegram_id: int, username: str, full_name: str):
    """Создать или обновить профиль пользователя."""
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO users (telegram_id, username, full_name, registered_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name
        """, (telegram_id, username, full_name, now))
        conn.commit()


def get_user(telegram_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_id=?", (telegram_id,)
        ).fetchone()
        return dict(row) if row else None


# ─── subscriptions ───────────────────────────────────────────────────────────

def create_subscription(telegram_id: int, key_pool_id: int,
                        tariff_key: str, expires_at: str | None) -> int:
    """Создать подписку и пометить ключ как занятый."""
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO subscriptions (telegram_id, key_pool_id, tariff_key, assigned_at, expires_at, is_active) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (telegram_id, key_pool_id, tariff_key, now, expires_at),
        )
        conn.execute(
            "UPDATE key_pool SET is_used=1, used_by_telegram_id=? WHERE id=?",
            (telegram_id, key_pool_id),
        )
        conn.commit()
        return cur.lastrowid


def get_user_subscriptions(telegram_id: int) -> list:
    """Все активные подписки пользователя с conf_text."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT s.*, k.conf_text
            FROM subscriptions s
            JOIN key_pool k ON k.id = s.key_pool_id
            WHERE s.telegram_id = ? AND s.is_active = 1
            ORDER BY s.assigned_at DESC
        """, (telegram_id,)).fetchall()
        return [dict(r) for r in rows]


def get_subscription_by_id(sub_id: int):
    with get_conn() as conn:
        row = conn.execute("""
            SELECT s.*, k.conf_text
            FROM subscriptions s
            JOIN key_pool k ON k.id = s.key_pool_id
            WHERE s.id = ?
        """, (sub_id,)).fetchone()
        return dict(row) if row else None


def get_conf_text_by_sub(sub_id: int) -> str | None:
    """Вернуть conf_text ключа привязанного к подписке (до удаления)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT k.conf_text FROM subscriptions s "
            "JOIN key_pool k ON k.id = s.key_pool_id "
            "WHERE s.id = ?",
            (sub_id,),
        ).fetchone()
        return row["conf_text"] if row else None


def revoke_subscription(sub_id: int) -> bool:
    """Деактивировать подписку и УДАЛИТЬ ключ из пула (повторное использование невозможно)."""
    with get_conn() as conn:
        sub = conn.execute(
            "SELECT * FROM subscriptions WHERE id=?", (sub_id,)
        ).fetchone()
        if not sub:
            return False
        key_pool_id = sub["key_pool_id"]
        # Удаляем ВСЕ подписки (активные и нет) ссылающиеся на этот ключ
        conn.execute("DELETE FROM subscriptions WHERE key_pool_id=?", (key_pool_id,))
        # Обнуляем legacy-ссылку в users (если есть)
        conn.execute("UPDATE users SET key_pool_id=NULL WHERE key_pool_id=?", (key_pool_id,))
        # Полностью удаляем ключ из пула — повторная выдача невозможна
        conn.execute("DELETE FROM key_pool WHERE id=?", (key_pool_id,))
        conn.commit()
        return True


def revoke_user_all(telegram_id: int) -> int:
    """Отозвать все активные подписки пользователя. Возвращает кол-во."""
    subs = get_user_subscriptions(telegram_id)
    count = 0
    for s in subs:
        if revoke_subscription(s["id"]):
            count += 1
    return count


def get_expiring_subscriptions(days: int) -> list:
    """Подписки, истекающие в течение `days` дней (ещё не уведомлённые)."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT s.*, k.conf_text
            FROM subscriptions s
            JOIN key_pool k ON k.id = s.key_pool_id
            WHERE s.is_active = 1
              AND s.expires_at IS NOT NULL
              AND s.warned_3d = 0
              AND datetime(s.expires_at) <= datetime('now', ? || ' days')
              AND datetime(s.expires_at) > datetime('now')
        """, (f"+{days}",)).fetchall()
        return [dict(r) for r in rows]


def get_expiring_subscriptions_hours(hours: int) -> list:
    """Подписки, истекающие в течение `hours` часов (ещё не уведомлённые для этого порога)."""
    warn_col = f"warned_{hours}h"
    with get_conn() as conn:
        rows = conn.execute(f"""
            SELECT s.*, k.conf_text
            FROM subscriptions s
            JOIN key_pool k ON k.id = s.key_pool_id
            WHERE s.is_active = 1
              AND s.expires_at IS NOT NULL
              AND s.{warn_col} = 0
              AND datetime(s.expires_at) <= datetime('now', '+{hours} hours')
              AND datetime(s.expires_at) > datetime('now')
        """).fetchall()
        return [dict(r) for r in rows]


def mark_warned(sub_id: int, level: str):
    """Отметить что уведомление отправлено. level: '3d' или '3h'."""
    col = f"warned_{level}"
    with get_conn() as conn:
        conn.execute(f"UPDATE subscriptions SET {col}=1 WHERE id=?", (sub_id,))
        conn.commit()


def get_expired_subscriptions() -> list:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM subscriptions
            WHERE is_active = 1
              AND expires_at IS NOT NULL
              AND datetime(expires_at) <= datetime('now')
        """).fetchall()
        return [dict(r) for r in rows]


def expire_subscription(sub_id: int):
    sub = get_subscription_by_id(sub_id)
    if not sub:
        return
    revoke_subscription(sub_id)


# ─── Stats & Admin ───────────────────────────────────────────────────────────

def get_stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM key_pool").fetchone()[0]
        free  = conn.execute("SELECT COUNT(*) FROM key_pool WHERE is_used=0").fetchone()[0]
        subs  = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE is_active=1").fetchone()[0]
        users = conn.execute(
            "SELECT COUNT(DISTINCT telegram_id) FROM subscriptions WHERE is_active=1"
        ).fetchone()[0]
        return {"total": total, "free": free, "used": total - free, "subs": subs, "users": users}


def get_all_active_users_with_subs() -> list:
    """Список пользователей с количеством активных подписок."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT u.telegram_id, u.username, u.full_name,
                   COUNT(s.id) as sub_count,
                   MIN(s.expires_at) as earliest_exp
            FROM users u
            JOIN subscriptions s ON s.telegram_id = u.telegram_id AND s.is_active = 1
            GROUP BY u.telegram_id
            ORDER BY sub_count DESC
        """).fetchall()
        return [dict(r) for r in rows]


# ─── Legacy (совместимость со scheduler) ─────────────────────────────────────

def assign_key(telegram_id: int, username: str, full_name: str,
               key_pool_id: int, expires_at=None):
    """Legacy wrapper — используй create_subscription() в новом коде."""
    upsert_user(telegram_id, username, full_name)
    create_subscription(telegram_id, key_pool_id, "1m", expires_at)


def get_all_active_users() -> list:
    """Legacy для scheduler."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT DISTINCT u.telegram_id, u.username,
                   s.expires_at, s.key_pool_id
            FROM users u
            JOIN subscriptions s ON s.telegram_id = u.telegram_id AND s.is_active = 1
        """).fetchall()
        return [dict(r) for r in rows]


def revoke_user(telegram_id: int) -> bool:
    """Legacy wrapper."""
    count = revoke_user_all(telegram_id)
    return count > 0
