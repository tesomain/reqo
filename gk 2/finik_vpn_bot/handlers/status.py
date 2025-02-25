import logging
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from utils.db import get_user_status

router = Router()
logger = logging.getLogger(__name__)

@router.message(F.text == "📊 Статус")
async def status_handler(message: Message):
    user_id = message.from_user.id
    logging_extra = {"user_id": user_id}
    logger.info("Запрос статуса", extra=logging_extra)
    await message.delete()

    status = await get_user_status(user_id)
    if not status:
        await message.answer("Вы еще не зарегистрированы. Используйте /start.")
        return

    access = "☑️ Есть" if status["active"] else "❌ Нет"
    days_left = status["days_left"]
    sub_end = status["subscription_end"] or "Нет активной подписки"
    invited = status["invited"]
    ref_link = status["referral_link"]

    text = (
        f"📊 Статус:\n"
        f"Доступ: {access}\n"
        f"├ Осталось дней: {days_left}\n"
        f"└ Активна до (МСК): {sub_end}\n\n"
        f"Реферальная ссылка:\n"
        f"└ `{ref_link}`\n"
        f"⬆️ Приглашайте друзей и получайте 3 дня за каждую их подписку!\n\n"
        f"Статистика рефералов:\n"
        f"└ Приглашено друзей: {invited}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Поделиться ссылкой", url=ref_link)],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="clear_message")]
    ])
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

def setup_status_handlers(dp: Router):
    dp.include_router(router)