from aiogram import F, Router
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, \
    CallbackQuery
from utils.db import get_user_status, register_referral
from utils.marzban import get_marzban_token, get_available_inbounds, create_vpn_user
from config import ADMIN_ID
import logging
import asyncio
from asyncio import gather

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text.startswith("/start"))
async def start_command(message: Message):
    user_id = message.from_user.id
    logging_extra = {"user_id": user_id}
    logger.info(f"Обработка /start, text={message.text}", extra=logging_extra)
    await message.delete()

    username = message.from_user.username or message.from_user.first_name
    status = await get_user_status(user_id)

    inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Начать установку", callback_data="start_install")]
    ])

    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].split("_")[1])
            logging_extra["referrer_id"] = referrer_id
            if referrer_id != user_id:
                success = await register_referral(referrer_id, user_id)
                if success:
                    welcome_text = (
                        f"Привет, {username}!\n"
                        f"Вы успешно зарегистрированы по ссылке друга.\n"
                        f"Купите подписку, чтобы начать!\n\n"
                        f"Выберите действие:"
                    )
                    try:
                        await message.bot.send_message(
                            referrer_id,
                            f"🎉 Пользователь @{username} зарегистрировался по вашей ссылке! "
                            f"Вы получите 3 дня подписки, когда он активирует подписку."
                        )
                    except Exception as e:
                        logger.error(f"Ошибка уведомления referrer_id={referrer_id}: {str(e)}", extra=logging_extra)
                else:
                    welcome_text = (
                        f"Привет, {username}!\n"
                        f"Вы уже зарегистрированы по этой ссылке.\n"
                        f"Купите подписку, чтобы продолжить!\n\n"
                        f"Выберите действие:"
                    )
            else:
                welcome_text = (
                    f"Привет, {username}!\n"
                    f"Нельзя пригласить самого себя.\n\n"
                    f"Выберите действие:"
                )
        except (ValueError, IndexError) as e:
            logger.error(f"Некорректный реферальный код: {str(e)}", extra=logging_extra)
            welcome_text = (
                f"Привет, {username}!\n"
                f"Ошибка в реферальной ссылке.\n\n"
                f"Выберите действие:"
            )
    else:
        if not status:
            await register_referral(None, user_id)
            welcome_text = (
                f"Привет, {username}!\n"
                f"Добро пожаловать в ФИНИК 🛰️\n"
                f"Приобретите подписку, чтобы начать!\n\n"
                f"Выберите действие:"
            )
        else:
            welcome_text = (
                f"Привет, {username}!\n"
                f"Вы уже зарегистрированы.\n"
                f"Купите подписку или проверьте статус!\n\n"
                f"Выберите действие:"
            )

    logger.info("Отправляем приветственное сообщение", extra=logging_extra)
    await message.answer(f"{welcome_text}\n\n👇👇👇", reply_markup=inline_keyboard)


@router.callback_query(F.data == "start_install")
async def start_install(callback: CallbackQuery):
    user_id = callback.from_user.id
    logging_extra = {"user_id": user_id}
    logger.info("Нажата кнопка 'Начать установку'", extra=logging_extra)
    await callback.message.delete()

    reply_keyboard = ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text="💳 Купить"), KeyboardButton(text="📊 Статус")],
            [KeyboardButton(text="⚙️ Установить"), KeyboardButton(text="🛠️ Тех. поддержка")]
        ]
    )
    text = "Выберите устройство:"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 iPhone", callback_data="device_iphone")],
        [InlineKeyboardButton(text="🤖 Android", callback_data="device_android")],
        [InlineKeyboardButton(text="💻 MacBook", callback_data="device_mac")],
        [InlineKeyboardButton(text="🖥️ Windows", callback_data="device_windows")]
    ])
    await callback.message.answer(text, reply_markup=reply_keyboard)
    await callback.message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("device_"))
async def device_selected(callback: CallbackQuery):
    user_id = callback.from_user.id
    device = callback.data.split("_")[1]
    logging_extra = {"user_id": user_id}
    logger.info(f"Выбрано устройство {device}", extra=logging_extra)
    await callback.message.delete()

    status = await get_user_status(user_id)
    reply_keyboard = ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text="💳 Купить"), KeyboardButton(text="📊 Статус")],
            [KeyboardButton(text="⚙️ Установить"), KeyboardButton(text="🛠️ Тех. поддержка")]
        ]
    )

    if not status["active"]:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Купить", callback_data="buy_subscription")]
        ])
        await callback.message.answer(
            "❌ У вас нет активной подписки. Пополните баланс через 'Купить'.",
            reply_markup=keyboard
        )
        return

    if not status["vpn_key"]:
        token = await get_marzban_token()
        if not token:
            logger.error("Не удалось получить токен Marzban", extra=logging_extra)
            await callback.message.answer("❌ Ошибка сервера. Попробуйте позже.")
            return
        username = f"user_{user_id}"
        inbounds = await get_available_inbounds(token)
        if not inbounds:
            logger.error("Не удалось получить inbounds", extra=logging_extra)
            await callback.message.answer("❌ Ошибка сервера. Обратитесь в техподдержку.")
            return
        vpn_key = await create_vpn_user(token, username, inbounds)
        if not vpn_key or not vpn_key.get("subscription_url"):
            logger.error("Не удалось создать ключ", extra=logging_extra)
            await callback.message.answer("❌ Ошибка создания ключа. Обратитесь в техподдержку.")
            return
        await save_vpn_key(user_id, vpn_key["subscription_url"])
        status = await get_user_status(user_id)

    v2raytun_url = f"https://apps.artydev.ru/?url=v2raytun://import/{status['vpn_key']}#FinikVPN"
    instruction = (
        "🌟 *Как подключиться?:*\n"
        "1️⃣ Нажми кпопку скачать.\n"
        "2️⃣ Нажми кнопку подключиться!"
    )
    if device == "iphone":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Скачать", url="https://apps.apple.com/kz/app/v2raytun/id6476628951")],
            [InlineKeyboardButton(text="🔗 Подключиться", url=v2raytun_url)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_devices")]
        ])
        await callback.message.answer(
            f"📱 *Вы выбрали iPhone:*\n\n{instruction}\n\nВыберите действие:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    elif device == "android":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Скачать",
                                  url="https://play.google.com/store/apps/details?id=com.v2raytun.android")],
            [InlineKeyboardButton(text="🔗 Подключиться", url=v2raytun_url)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_devices")]
        ])
        await callback.message.answer(
            f"🤖 *Вы выбрали Android:*\n\n{instruction}\n\nВыберите действие:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    elif device == "mac":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Скачать", url="https://apps.apple.com/kz/app/v2raytun/id6476628951")],
            [InlineKeyboardButton(text="🔗 Подключиться", url=v2raytun_url)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_devices")]
        ])
        await callback.message.answer(
            f"💻 *Вы выбрали MacBook:*\n\n{instruction}\n\nВыберите действие:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    elif device == "windows":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Скачать", url="https://ru.ldplayer.net/apps/v2raytun-on-pc.html")],
            [InlineKeyboardButton(text="🔗 Подключиться", url=v2raytun_url)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_devices")]
        ])
        await callback.message.answer(
            f"🖥️ *Вы выбрали Windows:*\n\n{instruction}\n\nВыберите действие:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )


@router.callback_query(F.data == "buy_subscription")
async def buy_subscription_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    logging_extra = {"user_id": user_id}
    logger.info("Нажата инлайн-кнопка 'Купить'", extra=logging_extra)
    await callback.message.delete()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 149 ₽ - 1 месяц", callback_data="buy_30")],
        [InlineKeyboardButton(text="💰 370 ₽ - 3 месяца", callback_data="buy_90")],
        [InlineKeyboardButton(text="💰 625 ₽ - 6 месяцев", callback_data="buy_180")]
    ])
    await callback.message.answer("Выберите подписку:", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "back_to_devices")
async def back_to_devices(callback: CallbackQuery):
    user_id = callback.from_user.id
    logging_extra = {"user_id": user_id}
    logger.info("Нажата кнопка 'Назад'", extra=logging_extra)
    await callback.message.delete()

    text = "Выберите устройство:"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 iPhone", callback_data="device_iphone")],
        [InlineKeyboardButton(text="🤖 Android", callback_data="device_android")],
        [InlineKeyboardButton(text="💻 MacBook", callback_data="device_mac")],
        [InlineKeyboardButton(text="🖥️ Windows", callback_data="device_windows")]
    ])
    await callback.message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "clear_message")
async def clear_message(callback: CallbackQuery):
    user_id = callback.from_user.id
    logging_extra = {"user_id": user_id}
    logger.info("Нажата кнопка 'Назад' для удаления сообщения", extra=logging_extra)
    await callback.message.delete()
    await callback.answer()


@router.message(F.text == "🛠️ Тех. поддержка")
async def support_handler(message: Message):
    user_id = message.from_user.id
    logging_extra = {"user_id": user_id}
    logger.info("Запрос техподдержки", extra=logging_extra)
    await message.delete()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📞 Связаться с поддержкой", url="tg://resolve?domain=teso001")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="clear_message")]
    ])
    await message.answer("Перейдите для связи с техподдержкой:", reply_markup=keyboard)


@router.message(F.text == "⚙️ Установить")
async def install_handler(message: Message):
    user_id = message.from_user.id
    logging_extra = {"user_id": user_id}
    logger.info("Нажата кнопка 'Установить'", extra=logging_extra)
    await message.delete()

    text = "Выберите устройство:"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 iPhone", callback_data="device_iphone")],
        [InlineKeyboardButton(text="🤖 Android", callback_data="device_android")],
        [InlineKeyboardButton(text="💻 MacBook", callback_data="device_mac")],
        [InlineKeyboardButton(text="🖥️ Windows", callback_data="device_windows")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="clear_message")]
    ])
    await message.answer(text, reply_markup=keyboard)


@router.message(F.text.startswith("/broadcast"))
async def broadcast_command(message: Message):
    user_id = message.from_user.id
    logging_extra = {"user_id": user_id}

    if user_id != ADMIN_ID:
        logger.info(f"Попытка рассылки от неадмина: user_id={user_id}", extra=logging_extra)
        await message.reply("Эта команда доступна только администратору!")
        return

    broadcast_text = message.text.split(maxsplit=1)
    if len(broadcast_text) < 2:
        await message.reply("Укажите текст для рассылки после /broadcast, например: /broadcast Привет всем!")
        return

    broadcast_message = broadcast_text[1]
    logger.info(f"Начало рассылки от user_id={user_id}: {broadcast_message}", extra=logging_extra)

    from utils.db import init_db_pool
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id FROM users")

    success_count = 0
    fail_count = 0
    batch_size = 20  # Максимум 20 сообщений в секунду для Telegram
    user_ids = [user["user_id"] for user in users]

    # Обрабатываем пользователей группами по 20
    for i in range(0, len(user_ids), batch_size):
        batch = user_ids[i:i + batch_size]
        tasks = []
        for uid in batch:
            tasks.append(message.bot.send_message(uid, broadcast_message))

        # Параллельная отправка в пределах группы
        results = await gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Ошибка отправки пользователю: {str(result)}", extra=logging_extra)
                fail_count += 1
            else:
                success_count += 1

        # Задержка между группами для соблюдения лимита в 20 сообщений/сек
        if i + batch_size < len(user_ids):
            await asyncio.sleep(1)  # 1 секунда между группами

    await message.reply(f"Рассылка завершена!\nУспешно: {success_count}\nНе удалось: {fail_count}")
    logger.info(f"Рассылка завершена: Успешно={success_count}, Не удалось={fail_count}", extra=logging_extra)


def setup_start_handlers(dp: Router):
    logger.info("Регистрация обработчиков start")
    dp.include_router(router)