from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from config import YUKASSA_SHOP_ID, YUKASSA_SECRET_KEY, TELEGRAM_BOT_TOKEN
from utils.db import extend_subscription, get_user_status, save_vpn_key, activate_referral_bonus, init_db_pool
from utils.marzban import get_marzban_token, enable_vpn_user, get_available_inbounds, create_vpn_user, get_vpn_user, delete_vpn_user
import uuid
import requests
import base64
import logging
import asyncio
from aiogram import Bot

bot = Bot(token=TELEGRAM_BOT_TOKEN)

logger = logging.getLogger(__name__)
router = Router()
_processed_payments = set()
# Временное хранилище для message_id (user_id -> {subscription_msg_id, payment_msg_id})
_message_ids = {}


@router.message(F.text == "💳 Купить")
async def buy_handler(message: Message):
    user_id = message.from_user.id
    logging_extra = {"user_id": user_id}
    logger.info("Нажата кнопка 'Купить'", extra=logging_extra)
    await message.delete()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 149 ₽ - 1 месяц", callback_data="buy_30")],
        [InlineKeyboardButton(text="💰 370 ₽ - 3 месяца", callback_data="buy_90")],
        [InlineKeyboardButton(text="💰 625 ₽ - 6 месяцев", callback_data="buy_180")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="clear_message")]
    ])
    msg = await message.answer("Выберите подписку:", reply_markup=keyboard)
    # Сохраняем message_id меню подписок
    _message_ids[user_id] = {"subscription_msg_id": msg.message_id, "payment_msg_id": None}


async def generate_payment_url(user_id: int, amount: int, days: int, order_id: str) -> tuple[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Idempotence-Key": order_id,
        "Authorization": f"Basic {base64.b64encode(f'{YUKASSA_SHOP_ID}:{YUKASSA_SECRET_KEY}'.encode()).decode()}"
    }
    payload = {
        "amount": {"value": f"{amount}.00", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": "https://t.me/finik_vpn_bot"},
        "capture": True,
        "description": f"Подписка на {days} дней для user_{user_id}",
        "metadata": {"user_id": str(user_id), "days": str(days), "order_id": order_id},
        "receipt": {
            "customer": {"email": "support@finik.online"},
            "items": [
                {
                    "description": f"Подписка на {days} дней",
                    "quantity": "1.00",
                    "amount": {"value": f"{amount}.00", "currency": "RUB"},
                    "vat_code": 1,
                    "payment_subject": "service",
                    "payment_mode": "full_payment"
                }
            ]
        }
    }
    response = requests.post("https://api.yookassa.ru/v3/payments", json=payload, headers=headers)
    if response.status_code == 200:
        return response.json()["confirmation"]["confirmation_url"], response.json()["id"]
    logger.error(f"Ошибка создания платежа: {response.text}", extra={"user_id": user_id})
    return None, None


@router.callback_query(F.data == "buy_30")
async def buy_30_days(callback: CallbackQuery):
    user_id = callback.from_user.id
    logging_extra = {"user_id": user_id}
    logger.info("Выбрана подписка на 30 дней", extra=logging_extra)
    await callback.message.delete()

    order_id = str(uuid.uuid4())
    payment_url, payment_id = await generate_payment_url(user_id, 149, 30, order_id)
    if not payment_url:
        await callback.message.answer("❌ Ошибка создания платежа. Попробуйте позже.")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Оплатить", url=payment_url)],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_subscriptions")]
    ])
    msg = await callback.message.answer("Оплата 30 дней: 149 рублей", reply_markup=keyboard)
    # Обновляем message_id для сообщения оплаты
    if user_id in _message_ids:
        _message_ids[user_id]["payment_msg_id"] = msg.message_id
    else:
        _message_ids[user_id] = {"subscription_msg_id": None, "payment_msg_id": msg.message_id}
    await callback.answer()


@router.callback_query(F.data == "buy_90")
async def buy_90_days(callback: CallbackQuery):
    user_id = callback.from_user.id
    logging_extra = {"user_id": user_id}
    logger.info("Выбрана подписка на 90 дней", extra=logging_extra)
    await callback.message.delete()

    order_id = str(uuid.uuid4())
    payment_url, payment_id = await generate_payment_url(user_id, 370, 90, order_id)
    if not payment_url:
        await callback.message.answer("❌ Ошибка создания платежа. Попробуйте позже.")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Оплатить", url=payment_url)],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_subscriptions")]
    ])
    msg = await callback.message.answer("Оплата 90 дней: 370 рублей", reply_markup=keyboard)
    if user_id in _message_ids:
        _message_ids[user_id]["payment_msg_id"] = msg.message_id
    else:
        _message_ids[user_id] = {"subscription_msg_id": None, "payment_msg_id": msg.message_id}
    await callback.answer()


@router.callback_query(F.data == "buy_180")
async def buy_180_days(callback: CallbackQuery):
    user_id = callback.from_user.id
    logging_extra = {"user_id": user_id}
    logger.info("Выбрана подписка на 180 дней", extra=logging_extra)
    await callback.message.delete()

    order_id = str(uuid.uuid4())
    payment_url, payment_id = await generate_payment_url(user_id, 625, 180, order_id)
    if not payment_url:
        await callback.message.answer("❌ Ошибка создания платежа. Попробуйте позже.")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Оплатить", url=payment_url)],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_subscriptions")]
    ])
    msg = await callback.message.answer("Оплата 180 дней: 625 рублей", reply_markup=keyboard)
    if user_id in _message_ids:
        _message_ids[user_id]["payment_msg_id"] = msg.message_id
    else:
        _message_ids[user_id] = {"subscription_msg_id": None, "payment_msg_id": msg.message_id}
    await callback.answer()


@router.callback_query(F.data == "back_to_subscriptions")
async def back_to_subscriptions(callback: CallbackQuery):
    user_id = callback.from_user.id
    logging_extra = {"user_id": user_id}
    logger.info("Нажата кнопка 'Назад' к выбору подписок", extra=logging_extra)
    await callback.message.delete()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 149 ₽ - 1 месяц", callback_data="buy_30")],
        [InlineKeyboardButton(text="💰 370 ₽ - 3 месяца", callback_data="buy_90")],
        [InlineKeyboardButton(text="💰 625 ₽ - 6 месяцев", callback_data="buy_180")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="clear_message")]
    ])
    msg = await callback.message.answer("Выберите подписку:", reply_markup=keyboard)
    _message_ids[user_id] = {"subscription_msg_id": msg.message_id, "payment_msg_id": None}
    await callback.answer()


@router.callback_query(F.data == "clear_message")
async def clear_message(callback: CallbackQuery):
    user_id = callback.from_user.id
    logging_extra = {"user_id": user_id}
    logger.info("Нажата кнопка 'Назад' для удаления сообщения", extra=logging_extra)
    await callback.message.delete()
    if user_id in _message_ids:
        del _message_ids[user_id]  # Очищаем хранилище для пользователя
    await callback.answer()


async def proc_payment(user_id, days, order_id, payment_id):
    logging_extra = {"user_id": user_id}
    logger.info(f"Обрабатываем оплату payment_id={payment_id}, days={days}", extra=logging_extra)
    if payment_id in _processed_payments:
        logger.info("Платеж уже обработан", extra=logging_extra)
        return
    _processed_payments.add(payment_id)
    logger.info(f"Продлеваем подписку days={days}", extra=logging_extra)
    await extend_subscription(user_id, days)

    status = await get_user_status(user_id)
    token = await get_marzban_token()
    logger.info(f"token: {token}", extra=logging_extra)
    if token:
        username = f"user_{user_id}"
        if not status["vpn_key"]:
            user_data = await get_vpn_user(token, username)
            if user_data:
                delete_result = await delete_vpn_user(token, username)
                if not delete_result:
                    logger.error(f"Не удалось удалить существующего пользователя {username}", extra=logging_extra)
                    logger.info("❌ Ошибка сервера. Обратитесь в техподдержку.", extra=logging_extra)
                    return
                await asyncio.sleep(1)

            inbounds = await get_available_inbounds(token)
            if not inbounds:
                logger.error("Не удалось получить inbounds", extra=logging_extra)
                return
            vpn_key = await create_vpn_user(token, username, inbounds)
            if not vpn_key or not vpn_key.get("subscription_url"):
                logger.error("Не удалось создать ключ", extra=logging_extra)
                return
            await save_vpn_key(user_id, vpn_key["subscription_url"])
            status = await get_user_status(user_id)
        await enable_vpn_user(token, username)

        pool = await init_db_pool()
        async with pool.acquire() as conn:
            referrers = await conn.fetch(
                "SELECT referrer_id FROM invited_users WHERE invited_user_id = $1 AND bonus_activated = FALSE",
                user_id
            )
        for referrer in referrers:
            referrer_id = referrer["referrer_id"]
            bonus_activated = await activate_referral_bonus(referrer_id, user_id)
            if bonus_activated:
                try:
                    await bot.send_message(
                        referrer_id,
                        f"🎉 Пользователь, которого вы пригласили, активировал подписку! Вам добавлено 3 дня."
                    )
                except Exception as e:
                    logger.error(f"Ошибка уведомления referrer_id={referrer_id}: {str(e)}", extra=logging_extra)

    # Удаляем оба сообщения, если они есть
    if user_id in _message_ids:
        for msg_key, msg_id in _message_ids[user_id].items():
            if msg_id:
                try:
                    await bot.delete_message(chat_id=user_id, message_id=msg_id)
                    logger.info(f"Удалено сообщение {msg_key}: message_id={msg_id}", extra=logging_extra)
                except Exception as e:
                    logger.error(f"Ошибка удаления {msg_key}: {str(e)}", extra=logging_extra)
        del _message_ids[user_id]  # Очищаем после удаления

    await bot.send_message(user_id,
                           f"✅ Оплата прошла успешно! Доступ продлён до {status['subscription_end']} (МСК).\n"
                           f"Теперь выберите устройство в меню 'Установить'.")


def setup_subscription_handlers(dp: Router):
    dp.include_router(router)