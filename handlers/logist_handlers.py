import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from states.logist_states import LogistStates
from keyboards.logist_keyboards import contact_keyboard, logist_main_menu, objects_keyboard, object_action_menu
from keyboards.kassa_keyboards import choose_system_menu
from services.logist_sheets import check_and_update_user_by_phone, get_active_objects, save_logist_report, get_delivered_messages
from services.google_sheets import is_allowed_user
from config import LOGIST_GROUP_ID

router = Router()

@router.message(F.text == "🚚 Logistika tizimi")
async def enter_logistika_system(message: Message, state: FSMContext):
    allowed, name = is_allowed_user(message.from_user.id)
    if allowed:
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

@router.message(F.text == "🔙 Chiqish / Bosh menyu")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Tizimni tanlang:", reply_markup=choose_system_menu())

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
    await state.set_state(LogistStates.waiting_for_object)

@router.message(LogistStates.waiting_for_object)
async def process_object_selection(message: Message, state: FSMContext):
    if message.text == "🔙 Chiqish / Bosh menyu":
        await state.clear()
        await message.answer("Tizimni tanlang:", reply_markup=choose_system_menu())
        return
        
    loading_msg = await message.answer("Tekshirilmoqda...")
    objects = get_active_objects()
    await loading_msg.delete()
    
    selected_obj = next((obj for obj in objects if obj['name'] == message.text), None)
    if not selected_obj:
        await message.answer("Kechirasiz, bunday obyekt topilmadi yoki u faol emas. Qayta tanlang:")
        return
        
    await state.update_data(object_id=selected_obj['id'], object_name=selected_obj['name'])
    await state.set_state(LogistStates.waiting_for_action)
    
    await message.answer(f"✅ <b>{selected_obj['name']}</b> tanlandi.\nQanday amalni bajaramiz?", reply_markup=object_action_menu(), parse_mode="HTML")

@router.message(LogistStates.waiting_for_action, F.text == "🔙 Orqaga")
async def action_back(message: Message, state: FSMContext):
    await show_active_objects(message, state)
    
@router.message(LogistStates.waiting_for_action, F.text == "📦 Yetkazilgan mahsulotlar")
async def show_delivered_products(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    object_id = data.get("object_id")
    object_name = data.get("object_name")
    
    if not LOGIST_GROUP_ID:
        await message.answer("Xatolik: LOGIST_GROUP_ID sozlanmagan.")
        return
        
    loading_msg = await message.answer("Oldingi hisobotlar yuklanmoqda...")
    messages = get_delivered_messages(object_id)
    await loading_msg.delete()
    
    if not messages:
        await message.answer("Hozircha ushbu obyektga mahsulot yetkazilmagan (yoki hisobotlar yo'q).")
        return
        
    await message.answer(f"<b>{object_name}</b> uchun oldingi yetkazmalar:", parse_mode="HTML")
    for msg in messages:
        try:
            if msg.get("text_id") and msg["text_id"].isdigit():
                await bot.copy_message(chat_id=message.from_user.id, from_chat_id=LOGIST_GROUP_ID, message_id=int(msg["text_id"]))
            if msg.get("photo_id") and len(msg["photo_id"]) > 5:
                await bot.send_photo(message.from_user.id, msg["photo_id"])
            if msg.get("video_id") and len(msg["video_id"]) > 5:
                try:
                    await bot.send_video_note(message.from_user.id, msg["video_id"])
                except:
                    await bot.send_video(message.from_user.id, msg["video_id"])
        except Exception as e:
            logging.error(f"Copying old report error: {e}")
            
    await message.answer("Barcha topilgan xabarlar yuborildi.")


@router.message(LogistStates.waiting_for_action, F.text == "✅ Yetkazildi")
async def start_delivery_report(message: Message, state: FSMContext):
    from config import LOGIST_REQUIRE_TEXT, LOGIST_REQUIRE_PHOTO, LOGIST_REQUIRE_VIDEO
    
    # Ma'lumotlarni tozalash
    await state.update_data(text_content="", photo_id="", video_id="")
    
    if LOGIST_REQUIRE_TEXT:
        await message.answer("Yetkazilgan mahsulotlar nomini yozma kiriting (masalan: shurup, profil):", reply_markup=ReplyKeyboardRemove())
        await state.set_state(LogistStates.waiting_for_items_text)
    elif LOGIST_REQUIRE_PHOTO:
        await message.answer("Endi mahsulotlar rasmini yuboring:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(LogistStates.waiting_for_items_photo)
    elif LOGIST_REQUIRE_VIDEO:
        await message.answer("Endi video (yoki dumaloq video) yuboring:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(LogistStates.waiting_for_items_video)
    else:
        await finish_delivery_report(message, state, message.bot)

@router.message(LogistStates.waiting_for_items_text, F.text)
async def process_delivery_text(message: Message, state: FSMContext, bot: Bot):
    from config import LOGIST_REQUIRE_PHOTO, LOGIST_REQUIRE_VIDEO
    await state.update_data(text_content=message.text)
    
    if LOGIST_REQUIRE_PHOTO:
        await message.answer("Endi mahsulotlar rasmini yuboring:")
        await state.set_state(LogistStates.waiting_for_items_photo)
    elif LOGIST_REQUIRE_VIDEO:
        await message.answer("Endi video (yoki dumaloq video) yuboring:")
        await state.set_state(LogistStates.waiting_for_items_video)
    else:
        await finish_delivery_report(message, state, bot)

@router.message(LogistStates.waiting_for_items_photo, F.photo)
async def process_delivery_photo(message: Message, state: FSMContext, bot: Bot):
    from config import LOGIST_REQUIRE_VIDEO
    await state.update_data(photo_id=message.photo[-1].file_id)
    
    if LOGIST_REQUIRE_VIDEO:
        await message.answer("Endi video (yoki dumaloq video) yuboring:")
        await state.set_state(LogistStates.waiting_for_items_video)
    else:
        await finish_delivery_report(message, state, bot)

@router.message(LogistStates.waiting_for_items_video, F.video_note | F.video)
async def process_delivery_video(message: Message, state: FSMContext, bot: Bot):
    video_id = message.video_note.file_id if message.video_note else message.video.file_id
    await state.update_data(video_id=video_id)
    await finish_delivery_report(message, state, bot)

async def finish_delivery_report(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    object_id = data.get("object_id")
    object_name = data.get("object_name")
    text_content = data.get("text_content", "")
    photo_id = data.get("photo_id", "")
    video_id = data.get("video_id", "")
    
    allowed, name = is_allowed_user(message.from_user.id)
    logist_name = name if allowed else "Noma'lum"
    
    from config import LOGIST_GROUP_ID
    if not LOGIST_GROUP_ID:
        await message.answer("Xatolik: LOGIST_GROUP_ID sozlanmagan. Iltimos, adminga murojaat qiling.")
        return
        
    caption_html = f"🏢 <b>Obyekt:</b> {object_name}\n👤 <b>Logist:</b> {logist_name}"
    if text_content:
        caption_html += f"\n📦 <b>Qo'shimcha matn:</b>\n{text_content}"
    
    try:
        loading_msg = await message.answer("Xabarlar guruhga yuborilmoqda...")
        
        msg_photo = None
        if photo_id:
            msg_photo = await bot.send_photo(LOGIST_GROUP_ID, photo_id, caption=caption_html, parse_mode="HTML")
        elif text_content:
            msg_photo = await bot.send_message(LOGIST_GROUP_ID, caption_html, parse_mode="HTML")
            
        if video_id:
            try:
                await bot.send_video_note(LOGIST_GROUP_ID, video_id)
            except:
                await bot.send_video(LOGIST_GROUP_ID, video_id)
        
        # Save photo msg ID as text_id so Mijoz bot copies the photo with caption
        msg_id_to_save = str(msg_photo.message_id) if msg_photo else ""
        save_logist_report(message.from_user.id, object_id, msg_id_to_save, "", video_id)
        
        await loading_msg.delete()
        await message.answer("✅ Barcha ma'lumotlar qabul qilindi va guruhga yuborildi!", reply_markup=logist_main_menu())
        await state.clear()
        
    except Exception as e:
        import logging
        logging.error(f"Report forwarding error: {e}")
        await message.answer("Hisobotni guruhga yuborishda xatolik yuz berdi. Iltimos, qayta urinib ko'ring.")
