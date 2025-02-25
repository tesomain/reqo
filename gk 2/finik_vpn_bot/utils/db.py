import asyncpg
from config import DATABASE_URL
from datetime import datetime, timedelta
import logging
from aiocache import cached
from aiocache.serializers import PickleSerializer

logger = logging.getLogger(__name__)

_db_pool = None

async def init_db_pool():
    global _db_pool
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=20)
    return _db_pool

async def init_db():
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                subscription_end TIMESTAMP,
                invited INTEGER DEFAULT 0,
                referral_link TEXT,
                vpn_key TEXT
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS invited_users (
                referrer_id BIGINT,
                invited_user_id BIGINT,
                PRIMARY KEY (referrer_id, invited_user_id),
                FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                FOREIGN KEY (invited_user_id) REFERENCES users(user_id),
                bonus_activated BOOLEAN DEFAULT FALSE
            )
        ''')

async def add_user(user_id):
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        referral_link = f"https://t.me/finik_vpn_bot?start=ref_{user_id}"
        await conn.execute(
            "INSERT INTO users (user_id, subscription_end, referral_link, vpn_key) "
            "VALUES ($1, NULL, $2, NULL) ON CONFLICT (user_id) DO NOTHING",
            user_id, referral_link
        )

async def extend_subscription(user_id, days):
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        current_end = await conn.fetchval("SELECT subscription_end FROM users WHERE user_id = $1", user_id)
        new_end = (current_end or datetime.now()) + timedelta(days=days)
        await conn.execute("UPDATE users SET subscription_end = $1 WHERE user_id = $2", new_end, user_id)

async def save_vpn_key(user_id, vpn_key):
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET vpn_key = $1 WHERE user_id = $2", vpn_key, user_id)

async def get_user_status(user_id):
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
    if not user:
        return None
    sub_end = user["subscription_end"]
    active = sub_end and sub_end > datetime.now()
    days_left = (sub_end - datetime.now()).days if sub_end and active else 0
    status = {
        "active": active,
        "days_left": days_left,
        "subscription_end": sub_end.strftime("%Y-%m-%d %H:%M:%S") if sub_end else None,
        "invited": user["invited"],
        "referral_link": user["referral_link"],
        "vpn_key": user.get("vpn_key", None)
    }
    return status

async def register_referral(referrer_id, invited_user_id):
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        try:
            async with conn.transaction():
                existing_user = await conn.fetchval("SELECT user_id FROM users WHERE user_id = $1", invited_user_id)
                if not existing_user:
                    referral_link = f"https://t.me/finik_vpn_bot?start=ref_{invited_user_id}"
                    await conn.execute(
                        "INSERT INTO users (user_id, subscription_end, referral_link, vpn_key) "
                        "VALUES ($1, NULL, $2, NULL)", invited_user_id, referral_link
                    )

                if referrer_id is None or referrer_id == invited_user_id:
                    return False

                already_invited = await conn.fetchval(
                    "SELECT COUNT(*) FROM invited_users WHERE referrer_id = $1 AND invited_user_id = $2",
                    referrer_id, invited_user_id
                )
                if already_invited == 0:
                    await conn.execute(
                        "INSERT INTO invited_users (referrer_id, invited_user_id, bonus_activated) "
                        "VALUES ($1, $2, FALSE) ON CONFLICT DO NOTHING",
                        referrer_id, invited_user_id
                    )
                    await conn.execute(
                        "UPDATE users SET invited = invited + 1 WHERE user_id = $1",
                        referrer_id
                    )
                    logger.info(f"Реферал зарегистрирован: referrer_id={referrer_id}, invited_user_id={invited_user_id}")
                    return True
                logger.info(f"Реферал уже зарегистрирован: referrer_id={referrer_id}, invited_user_id={invited_user_id}")
                return False
        except Exception as e:
            logger.error(f"Ошибка регистрации реферала: {str(e)}")
            return False

async def activate_referral_bonus(referrer_id, invited_user_id):
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        try:
            async with conn.transaction():
                bonus_exists = await conn.fetchval(
                    "SELECT bonus_activated FROM invited_users WHERE referrer_id = $1 AND invited_user_id = $2",
                    referrer_id, invited_user_id
                )
                if bonus_exists is False:
                    await conn.execute(
                        "UPDATE invited_users SET bonus_activated = TRUE WHERE referrer_id = $1 AND invited_user_id = $2",
                        referrer_id, invited_user_id
                    )
                    await extend_subscription(referrer_id, 3)
                    logger.info(f"Бонус 3 дня начислен для referrer_id={referrer_id}")
                    return True
                logger.info(f"Бонус уже активирован для referrer_id={referrer_id}, invited_user_id={invited_user_id}")
                return False
        except Exception as e:
            logger.error(f"Ошибка активации бонуса: {str(e)}")
            return False

async def get_invited_count(referrer_id):
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM invited_users WHERE referrer_id = $1", referrer_id
        )
    return count