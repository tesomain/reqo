import aiohttp
import logging
from config import MARZBAN_URL, ADMIN_USERNAME, ADMIN_PASSWORD
from aiocache import cached

logger = logging.getLogger(__name__)

@cached(ttl=3600)  # Кэшируем токен на 1 час
async def get_marzban_token():
    payload = {"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
    logger.info(f"Попытка получить токен с MARZBAN_URL={MARZBAN_URL}")
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{MARZBAN_URL}/api/admin/token",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            ssl=False
        ) as response:
            logger.info(f"Статус ответа от Marzban: {response.status}")
            if response.status == 200:
                data = await response.json()
                return data["access_token"]
            logger.error(f"Ошибка получения токена: {response.status} - {await response.text()}")
            return None

async def get_available_inbounds(token):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{MARZBAN_URL}/api/inbounds",
            headers={"Authorization": f"Bearer {token}"},
            ssl=False
        ) as response:
            if response.status == 200:
                data = await response.json()
                logger.info(f"Доступные inbounds: {data}")
                return data
            logger.error(f"Ошибка получения inbound'ов: {response.status} - {await response.text()}")
            return None

async def get_vpn_user(token, username):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{MARZBAN_URL}/api/user/{username}",
            headers={"Authorization": f"Bearer {token}"},
            ssl=False
        ) as response:
            logger.info(f"Ответ на запрос данных {username}: {response.status}")
            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                logger.info(f"Пользователь {username} не найден в Marzban")
                return None
            logger.error(f"Ошибка получения данных пользователя {username}: {response.status}")
            return None

async def create_vpn_user(token, username, inbounds):
    if not inbounds or "vless" not in inbounds or not inbounds["vless"]:
        logger.error(f"Нет доступных vless inbound'ов для создания пользователя {username}")
        return None
    inbound_tag = inbounds["vless"][0]["tag"]
    inbound = {"vless": [inbound_tag]}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{MARZBAN_URL}/api/user",
            headers={"Authorization": f"Bearer {token}"},
            json={"username": username, "proxies": {"vless": {}}, "inbounds": inbound},
            ssl=False
        ) as response:
            if response.status == 200:
                return await response.json()
            logger.error(f"Ошибка создания пользователя {username}: {response.status} - {await response.text()}")
            return None

async def delete_vpn_user(token, username):
    async with aiohttp.ClientSession() as session:
        async with session.delete(
            f"{MARZBAN_URL}/api/user/{username}",
            headers={"Authorization": f"Bearer {token}"},
            ssl=False
        ) as response:
            logger.info(f"Ответ на удаление {username}: {response.status}")
            if response.status in (200, 204):
                logger.info(f"Пользователь {username} успешно удалён из Marzban")
                return True
            elif response.status == 404:
                logger.info(f"Пользователь {username} не найден в Marzban, пропускаем удаление")
                return True
            logger.error(f"Ошибка удаления пользователя {username}: {response.status}")
            return False

async def disable_vpn_user(token, username):
    async with aiohttp.ClientSession() as session:
        async with session.put(
            f"{MARZBAN_URL}/api/user/{username}",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": "disabled"},
            ssl=False
        ) as response:
            logger.info(f"Ответ на отключение {username}: {response.status}")
            if response.status == 200:
                logger.info(f"Ключ {username} успешно отключён")
                return True
            logger.error(f"Ошибка отключения ключа {username}: {response.status}")
            return False

async def enable_vpn_user(token, username):
    async with aiohttp.ClientSession() as session:
        async with session.put(
            f"{MARZBAN_URL}/api/user/{username}",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": "active"},
            ssl=False
        ) as response:
            if response.status == 200:
                logger.info(f"Ключ {username} успешно включён")
                return True
            logger.error(f"Ошибка включения ключа {username}: {response.status}")
            return False