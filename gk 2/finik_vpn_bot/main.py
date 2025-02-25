from aiogram import Bot, Dispatcher
from aiogram.types import Update
from handlers.start import setup_start_handlers
from handlers.status import setup_status_handlers
from handlers.subscription import setup_subscription_handlers
from handlers.subscription import proc_payment
from utils.scheduler import check_subscriptions, setup_scheduler
from utils.db import init_db_pool, init_db
from config import TELEGRAM_BOT_TOKEN
import asyncio
import logging
import logging.handlers
from aiohttp import web
import os
import ssl

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] [user_id:%(user_id)s] %(message)s",
    defaults={"user_id": "N/A"}
)

log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
file_handler = logging.handlers.RotatingFileHandler(
    os.path.join(log_dir, "bot.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5
)
file_handler.setFormatter(formatter)
memory_handler = logging.handlers.MemoryHandler(
    capacity=1024,
    flushLevel=logging.ERROR,
    target=file_handler
)
memory_handler.setFormatter(formatter)
logging.getLogger().addHandler(memory_handler)

bot = None
dp = None

# Обработчик вебхука Telegram
async def telegram_webhook(request):
    update = Update(**await request.json())
    await dp.process_update(update)
    return web.Response(text="OK", status=200)

# Обработчик вебхука ЮKassa
async def yookassa_webhook_handler(request):
    try:
        data = await request.json()
        logger.info(f"Получен вебхук от ЮKassa: {data}")

        event = data.get("event")
        payment_object = data.get("object", {})
        payment_id = payment_object.get("id")
        status = payment_object.get("status")
        metadata = payment_object.get("metadata", {})
        user_id = int(metadata.get("user_id"))
        days = int(metadata.get("days"))
        order_id = metadata.get("order_id")

        if event == "payment.succeeded" and status == "succeeded":
            logger.info(f"Платеж {payment_id} успешен для пользователя {user_id}")
            await proc_payment(user_id, days, order_id, payment_id)
        elif event == "payment.canceled" and status == "canceled":
            logger.info(f"Платеж {payment_id} отменен для пользователя {user_id}")
            await bot.send_message(user_id, "Ваш платеж был отменен.")

        return web.Response(text="OK", status=200)

    except Exception as e:
        logger.error(f"Ошибка обработки вебхука: {e}")
        return web.Response(text="Error", status=500)

# Настройка веб-сервера
async def setup_web_server():
    app = web.Application()
    app.add_routes([
        web.post('/telegram_webhook', telegram_webhook),  # Telegram вебхук
        web.post('/yookassa_webhook', yookassa_webhook_handler)  # ЮKassa вебхук
    ])
    runner = web.AppRunner(app)

    # Настройка SSL
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    ssl_context.load_cert_chain(
        certfile='/etc/letsencrypt/live/webhook.finik.online/fullchain.pem',
        keyfile='/etc/letsencrypt/live/webhook.finik.online/privkey.pem'
    )

    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 443, ssl_context=ssl_context)
    await site.start()
    logger.info("Веб-сервер запущен на порту 443")

# Установка вебхука Telegram
async def set_telegram_webhook():
    webhook_url = "https://webhook.finik.online/telegram_webhook"
    await bot.set_webhook(webhook_url)
    logger.info(f"Вебхук Telegram установлен: {webhook_url}")

async def main():
    global bot, dp
    logger.info("Инициализация бота")
    await init_db_pool()
    await init_db()
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    setup_start_handlers(dp)
    setup_status_handlers(dp)
    setup_subscription_handlers(dp)

    await setup_scheduler()
    await check_subscriptions()

    await set_telegram_webhook()
    await setup_web_server()

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())