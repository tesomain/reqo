# finik_vpn_bot/config.py
from dotenv import load_dotenv
import os

# Загружаем переменные из .env
load_dotenv()

# Получаем значения из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
MARZBAN_URL = os.getenv("MARZBAN_URL")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
YUKASSA_SHOP_ID = os.getenv("YUKASSA_SHOP_ID")
YUKASSA_SECRET_KEY = os.getenv("YUKASSA_SECRET_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # Преобразуем в int, так как это число