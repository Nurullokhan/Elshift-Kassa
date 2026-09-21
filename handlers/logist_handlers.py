import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from states.logist_states import LogistStates
from keyboards.logist_keyboards import contact_keyboard, logist_main_menu, objects_keyboard
from keyboards.kassa_keyboards import choose_system_menu
from services.logist_sheets import check_and_update_user_by_phone, get_active_objects, save_logist_report
from services.google_sheets import is_allowed_user
from config import LOGIST_GROUP_ID

router = Router()

@router.message(F.text == "🚚 Logistika tizimi")
async def enter_logistika_system(message: Message, state: FSMContext):
    allowed, name = is_allowed_user(message.from_user.id)
    if allowed:
        # In the future we can check if role == "Logist", but for now if they click it, show menu
        await message.answer(f"Xush kelibsiz, {name}! Siz logistika bo'limiga kirdingiz.", reply_markup=logist_main_menu())
        await state.clear()

@router.message(LogistStates.waiting_for_contact, F.contact)
async def process_contact(message: Message, state: FSMContext):
    phone_number = message.contact.phone_number
    telegram_id = message.from_user.id
    
    success, fullname, role = check_and_update_user_by_phone(phone_number, telegram_id)
    if success:
        await message.answer(f"Muvaffaqiyatli ro'yxatdan o'tdingiz, {fullname}!\n\nIltimos, tizimni tanlang:", reply_markup=choose_system_menu())
        await state.clear()
    else:
        await message.answer("⛔ Kechirasiz, sizda tizimdan foydalanish huquqi yo'q yoki raqam bazadan topilmadi.", reply_markup=ReplyKeyboardRemove())
        await state.clear()

@router.message(F.text == "🏢 Faol obyektlar")
async def show_active_objects(message: Message, state: FSMContext):
    allowed, name = is_allowed_user(message.from_user.id)
    if not allowed:
        return
        
    loading_msg = await message.answer("Obyektlar ro'yxati yuklanmoqda...")
    objects = get_active_objects()
    await loading_msg.delete()
    
    if not objects:
        await message.answer("Hozirgi vaqtda faol obyektlar topilmadi.")
        return
        
    await message.answer("Iltimos, hisobot yuboriladigan obyektni tanlang:", reply_markup=objects_keyboard(objects))

@router.callback_query(F.data.startswith("logist_obj_"))
async def select_object(call: CallbackQuery, state: FSMContext):
    object_id = call.data.replace("logist_obj_", "")
    object_name = "Obyekt"
    if call.message.reply_markup and call.message.reply_markup.inline_keyboard:
        for row in call.message.reply_markup.inline_keyboard:
            for btn in row:
                if btn.callback_data == call.data:
                    object_name = btn.text
                    break
                
    await state.update_data(object_id=object_id, object_name=object_name)
    await state.set_state(LogistStates.waiting_for_report)
    
    await call.message.edit_text(f"✅ <b>{object_name}</b> tanlandi.\n\nIltimos, yetkazib berish (delivery) haqida rasm, video yoki matnli hisobot yuboring.", parse_mode="HTML")
    await call.answer()

@router.message(F.text == "🔙 Chiqish / Bosh menyu")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Tizimni tanlang:", reply_markup=choose_system_menu())

@router.message(LogistStates.waiting_for_report)
async def process_report(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    object_id = data.get("object_id")
    object_name = data.get("object_name")
    
    allowed, name = is_allowed_user(message.from_user.id)
    logist_name = name if allowed else "Noma'lum"
    
    if not LOGIST_GROUP_ID:
        await message.answer("Xatolik: LOGIST_GROUP_ID sozlanmagan. Iltimos, adminga murojaat qiling.")
        return
        
    text_content = message.text or message.caption or "Yo'q"
    caption_html = f"🏢 <b>Obyekt:</b> {object_name}\n👤 <b>Logist:</b> {logist_name}\n📦 <b>Qo'shimcha matn:</b>\n{text_content}"
    
    try:
        sent_msg = None
        if message.photo:
            sent_msg = await bot.send_photo(LOGIST_GROUP_ID, message.photo[-1].file_id, caption=caption_html, parse_mode="HTML")
        elif message.video:
            sent_msg = await bot.send_video(LOGIST_GROUP_ID, message.video.file_id, caption=caption_html, parse_mode="HTML")
        elif message.video_note:
            sent_msg = await bot.send_video_note(LOGIST_GROUP_ID, message.video_note.file_id)
            await bot.send_message(LOGIST_GROUP_ID, caption_html, parse_mode="HTML", reply_to_message_id=sent_msg.message_id)
        else:
            sent_msg = await bot.send_message(LOGIST_GROUP_ID, caption_html, parse_mode="HTML")
            
        # Save to DB
        photo_id = message.photo[-1].file_id if message.photo else ""
        video_id = message.video.file_id if message.video else (message.video_note.file_id if message.video_note else "")
        text_id = str(sent_msg.message_id) if sent_msg else ""
        
        save_logist_report(message.from_user.id, object_id, text_id, photo_id, video_id)
        
        await message.answer("✅ Hisobot qabul qilindi va guruhga yuborildi!", reply_markup=logist_main_menu())
        await state.clear()
        
    except Exception as e:
        logging.error(f"Report forwarding error: {e}")
        await message.answer("Hisobotni guruhga yuborishda xatolik yuz berdi. Iltimos, qayta urinib ko'ring.")
