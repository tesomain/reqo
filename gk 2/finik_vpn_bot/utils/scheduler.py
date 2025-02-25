from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from utils.db import get_user_status, save_vpn_key, init_db_pool
from utils.marzban import disable_vpn_user, enable_vpn_user, get_marzban_token, create_vpn_user, get_available_inbounds, delete_vpn_user, get_vpn_user
from aiogram import Bot
from config import TELEGRAM_BOT_TOKEN
import asyncio
import logging

scheduler = AsyncIOScheduler()
bot = Bot(token=TELEGRAM_BOT_TOKEN)
logger = logging.getLogger(__name__)

async def process_user(user, token):
    user_id = user["user_id"]
    status = await get_user_status(user_id)
    username = f"user_{user_id}"

    current_time = datetime.now()
    logger.info(f"Проверка user_id={user_id}: active={status['active']}, days_left={status['days_left']}")

    user_data = await get_vpn_user(token, username)
    inbounds = await get_available_inbounds(token)
    if not inbounds:
        logger.error(f"Не удалось получить inbounds для user_id={user_id}")
        return

    if user_data:
        online_at = user_data.get("online_at")
        created_at = user_data.get("created_at")
        last_active = online_at or created_at
        if last_active:
            last_active_dt = datetime.fromisoformat(last_active.replace("Z", "+00:00"))
            if (current_time - last_active_dt).days >= 15 and not status["active"]:
                logger.info(f"Пользователь {username} неактивен более 15 дней, удаляем ключ")
                await delete_vpn_user(token, username)
                await save_vpn_key(user_id, None)
                user_data = None

    if not user_data or not status["vpn_key"]:
        vpn_key = await create_vpn_user(token, username, inbounds)
        if not vpn_key or not vpn_key.get("subscription_url"):
            logger.error(f"Не удалось создать пользователя {username} в Marzban")
            return
        await save_vpn_key(user_id, vpn_key["subscription_url"])
        logger.info(f"Пользователь {username} успешно создан в Marzban")

    if not status["active"]:
        await disable_vpn_user(token, username)
    elif status["active"]:
        await enable_vpn_user(token, username)

    if status["days_left"] == 3:
        await bot.send_message(user_id, "⚠️ Ваша подписка истекает через 3 дня! Продлите доступ в меню 'Купить'.")

async def check_subscriptions():
    logger.info("Запуск проверки подписок")
    pool = await init_db_pool()
    token = await get_marzban_token()
    if not token:
        logger.error("Не удалось получить токен Marzban")
        return

    async with pool.acquire() as conn:
        users = await conn.fetch("""
            SELECT user_id, subscription_end 
            FROM users 
            WHERE subscription_end IS NOT NULL 
            AND (subscription_end < $1 OR subscription_end > $2)
        """, datetime.now() + timedelta(days=7), datetime.now() - timedelta(days=1))

    logger.info(f"Найдено пользователей для проверки: {len(users)}")
    batch_size = 50
    for i in range(0, len(users), batch_size):
        batch = users[i:i + batch_size]
        tasks = [process_user(user, token) for user in batch]
        await asyncio.gather(*tasks)

async def setup_scheduler():
    logger.info("Настройка scheduler")
    scheduler.add_job(check_subscriptions, "interval", minutes=20)
    scheduler.start()