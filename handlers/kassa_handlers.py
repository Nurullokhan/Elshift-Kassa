import logging
import math
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from config import ADMIN_CHAT_ID
from states.kassa_states import KassaState
from states.logist_states import LogistStates
from keyboards.kassa_keyboards import main_menu, cancel_keyboard, choose_system_menu, undo_keyboard
from keyboards.logist_keyboards import contact_keyboard
from services.google_sheets import is_allowed_user, save_kassa, delete_kassa_entry, get_today_report, get_overall_report, get_last_user_entries
from services.google_sheets import _parse_amount

router = Router()

# Oxirgi saqlangan yozuv — bekor qilish uchun
# { telegram_id: {"entry": dict, "time": datetime, "tur": str, "summa": str, "izoh": str} }
_last_saved: dict[int, dict] = {}
UNDO_TTL = 300  # 5 daqiqa


# ─── Yordamchi ────────────────────────────────────────────────────────────────

def _fmt(n: float) -> str:
    return f"{int(n):,}".replace(",", " ")


def _try_number(s: str) -> tuple[int, str] | None:
    """
    Matnni raqam sifatida o'qishga harakat qiladi.
    Qo'llab-quvvatlaydi: 1.005.000 | 500$ | 1,005,000 | 500 000 | 500000
    Qaytaradi: (miqdor, 'som'|'usd') yoki None
    """
    s = s.strip()
    is_usd = '$' in s or 'dollar' in s.lower()
    # Valyuta belgisini, nuqta va vergullarni (ming ajratgich) olib tashlaymiz
    clean = (s.replace('$', '').replace('dollar', '').replace('Dollar', '')
              .replace('.', '').replace(',', '').replace(' ', '').strip())
    if not clean.isdigit() or int(clean) <= 0:
        return None
    return int(clean), 'usd' if is_usd else 'som'


def _parse_input(text: str) -> tuple[str | None, str | None, str | None]:
    """
    Ikki yo'nalishli parser — 'izoh - summa' yoki 'summa - izoh' tartibini
    avtomatik aniqlaydi.

    Misollar:
      'Alukabond shopiriga - 1.005.000'  →  ('1 005 000', 'so\'m', 'Alukabond shopiriga')
      '500$ - Zuhriddinga'               →  ('500',       '$',     'Zuhriddinga')
      '1 500 000 - Ish haqi'             →  ('1 500 000', 'so\'m', 'Ish haqi')

    Qaytaradi: (summa, valyuta, izoh) yoki (None, None, None)
    """
    # Ajratuvchi: bo'sh joy bilan ' - ' (afzal), yoki shunchaki '-'
    if ' - ' in text:
        parts = text.split(' - ', 1)
    elif '-' in text:
        parts = text.split('-', 1)
    else:
        return None, None, None

    left  = parts[0].strip()
    right = parts[1].strip()

    left_num  = _try_number(left)
    right_num = _try_number(right)

    # Qaysi tomon raqam ekanligini aniqlaymiz
    if left_num and not right_num:
        amount, valyuta = left_num
        izoh = right
    elif right_num and not left_num:
        amount, valyuta = right_num
        izoh = left
    else:
        return None, None, None  # ikkisi ham raqam yoki ikkisi ham matn

    if not izoh:
        return None, None, None

    # Summani formatlash (faqat raqam, valyuta alohida)
    summa_fmt = f"{amount:,}".replace(',', ' ')
    valyuta_str = "$" if valyuta == 'usd' else "so'm"

    return summa_fmt, valyuta_str, izoh


async def _notify_admin(bot: Bot, tur: str, summa: str, valyuta: str, izoh: str, from_user) -> None:
    if not ADMIN_CHAT_ID:
        return
    try:
        emoji = "💰" if tur == "Kirim" else "💸"
        uname = f"@{from_user.username}" if from_user.username else "—"
        await bot.send_message(
            ADMIN_CHAT_ID,
            f"{emoji} <b>{tur.upper()}</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💵 {summa} {valyuta} — {izoh}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 {from_user.full_name} ({uname})\n"
            f"🆔 <code>{from_user.id}</code>\n"
            f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode="HTML",
        )
    except Exception as e:
        logging.error(f"Admin xabari yuborilmadi: {e}")


# ─── /start ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    allowed, name = is_allowed_user(message.from_user.id)
    if not allowed:
        await message.answer("Tizimga kirish uchun telefon raqamingizni pastdagi tugma orqali yuboring:", reply_markup=contact_keyboard())
        await state.set_state(LogistStates.waiting_for_contact)
        return
        
    await message.answer(
        f"👋 Salom, <b>{name}</b>!\n\n"
        f"Iltimos, tizimni tanlang:",
        parse_mode="HTML",
        reply_markup=choose_system_menu(),
    )

@router.message(F.text == "💰 Kassa tizimi")
async def enter_kassa_system(message: Message, state: FSMContext):
    allowed, name = is_allowed_user(message.from_user.id)
    if not allowed:
        return
        
    await message.answer(
        f"<b>Elshift Kassa</b> bo'limiga xush kelibsiz!\n\n"
        f"Namuna: <code>100000 - Alukabond sotildi</code>",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


# ─── KIRIM / CHIQIM boshlash ──────────────────────────────────────────────────

@router.message(F.text == "💰 Kirim")
async def kirim_start(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(tur="Kirim")
    await state.set_state(KassaState.input)
    
    uid = message.from_user.id
    last_entries = get_last_user_entries(uid, "Kirim", 3)
    
    text = "💰 <b>Kirim</b>\n\nIzoh va summani <b>-</b> bilan ajratib yozing:\n\n"
    
    if last_entries:
        text += "📝 <b>Sizning oxirgi kiritganlaringiz (Namuna sifatida):</b>\n"
        for e in last_entries:
            s = _fmt(_parse_amount(e['summa'])) if e['summa'] else e['summa']
            text += f"▪️ <code>{e['izoh']} - {s} {e['valyuta']}</code>\n"
    else:
        text += (
            "<i>Namunalar:</i>\n"
            "<code>Mijozdan to'lov - 1.005.000</code>\n"
            "<code>Avans Hasanovdan - 500$</code>\n"
            "<code>1500000 - Savdo tushumi</code>"
        )
        
    await message.answer(text, parse_mode="HTML", reply_markup=cancel_keyboard())


@router.message(F.text == "💸 Chiqim")
async def chiqim_start(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(tur="Chiqim")
    await state.set_state(KassaState.input)
    
    uid = message.from_user.id
    last_entries = get_last_user_entries(uid, "Chiqim", 3)
    
    text = "💸 <b>Chiqim</b>\n\nIzoh va summani <b>-</b> bilan ajratib yozing:\n\n"
    
    if last_entries:
        text += "📝 <b>Sizning oxirgi kiritganlaringiz (Namuna sifatida):</b>\n"
        for e in last_entries:
            s = _fmt(_parse_amount(e['summa'])) if e['summa'] else e['summa']
            text += f"▪️ <code>{e['izoh']} - {s} {e['valyuta']}</code>\n"
    else:
        text += (
            "<i>Namunalar:</i>\n"
            "<code>Elektr to'lovi - 250.000</code>\n"
            "<code>Material xaridi - 1,500,000</code>\n"
            "<code>800000 - Ishchi maoshi</code>"
        )
        
    await message.answer(text, parse_mode="HTML", reply_markup=cancel_keyboard())


@router.message(F.text == "🔄 Ayirboshlash")
async def exchange_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(KassaState.exchange_input)
    await message.answer(
        "🔄 <b>Ayirboshlash</b>\n\n"
        "Chiqim qilinayotgan summa va valyuta kursini <b>-</b> bilan ajratib yozing:\n\n"
        "<b>Dollarni so'mga maydalash:</b>\n"
        "<code>100$ - 12600</code> (100$ chiqib, 1 260 000 so'm kiradi)\n\n"
        "<b>So'mni dollarga o'girish:</b>\n"
        "<code>1260000 - 12600</code> (so'm chiqib, 100$ kiradi)",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )


# ─── KIRITISH ─────────────────────────────────────────────────────────────────

@router.message(KassaState.input)
async def kassa_input(message: Message, state: FSMContext, bot: Bot):
    # Matn bo'lmasa (foto, sticker va boshqalar) — e'tiborsiz qoldiramiz
    if not message.text:
        await message.answer(
            "⚠️ Iltimos, matn ko'rinishida yozing.",
            reply_markup=cancel_keyboard(),
        )
        return

    text = message.text.strip()

    if text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=main_menu())
        return

    summa, valyuta, izoh = _parse_input(text)

    data = await state.get_data()
    tur  = data.get("tur", "Kirim")  # KeyError oldini olish
    uid  = message.from_user.id

    if summa is None:
        if tur == "Kirim":
            ex = (
                "<code>Mijozdan to'lov - 1.005.000</code>\n"
                "<code>Avans Hasanovdan - 500$</code>\n"
                "<code>1500000 - Savdo tushumi</code>"
            )
        else:
            ex = (
                "<code>Elektr to'lovi - 250.000</code>\n"
                "<code>Material xaridi - 1,500,000</code>\n"
                "<code>800000 - Ishchi maoshi</code>"
            )
            
        await message.answer(
            f"⚠️ Format noto'g'ri. Namunalar:\n\n{ex}\n\n"
            f"Izoh va summani <b> - </b> bilan ajrating.",
            parse_mode="HTML",
        )
        return

    ok, entry = save_kassa(uid, tur, summa, valyuta, izoh)
    await state.clear()

    if ok:
        _last_saved[uid] = {
            "entry": entry,
            "time":  datetime.now(),
            "tur":   tur,
            "summa": summa,
            "valyuta": valyuta,
            "izoh":  izoh,
        }
        emoji = "💰" if tur == "Kirim" else "💸"
        await message.answer(
            f"✅ <b>{tur} saqlandi!</b>\n\n"
            f"{emoji} {summa} {valyuta} — {izoh}",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
        await _notify_admin(bot, tur, summa, valyuta, izoh, message.from_user)
    else:
        await message.answer(
            "❌ Saqlashda xato yuz berdi. Qayta urinib ko'ring.",
            reply_markup=main_menu(),
        )


@router.message(KassaState.exchange_input)
async def exchange_input(message: Message, state: FSMContext, bot: Bot):
    # Matn bo'lmasa — e'tiborsiz qoldiramiz
    if not message.text:
        await message.answer(
            "⚠️ Iltimos, matn ko'rinishida yozing.",
            reply_markup=cancel_keyboard(),
        )
        return

    text = message.text.strip()
    if text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=main_menu())
        return

    if ' - ' in text:
        parts = text.split(' - ', 1)
    elif '-' in text:
        parts = text.split('-', 1)
    else:
        await message.answer(
            "⚠️ Format noto'g'ri. Masalan: <code>100$ - 12600</code>",
            parse_mode="HTML",
        )
        return

    amount_data = _try_number(parts[0])
    rate_data = _try_number(parts[1])

    if not amount_data or not rate_data:
        await message.answer(
            "⚠️ Raqam kiritishda xatolik.\n\n"
            "Masalan: <code>100$ - 12600</code> yoki <code>1260000 - 12600</code>",
            parse_mode="HTML",
        )
        return

    amount, valyuta_out = amount_data
    rate, _ = rate_data

    if rate <= 0:
        await message.answer("⚠️ Kurs noto'g'ri. Musbat son kiriting.")
        return

    uid = message.from_user.id
    vaqt = datetime.now()

    if valyuta_out == 'usd':
        chiqim_val = '$'
        chiqim_summa = amount
        kirim_val = "so'm"
        kirim_summa = math.floor((amount * rate) / 1000) * 1000
    else:
        chiqim_val = "so'm"
        chiqim_summa = amount
        kirim_val = "$"
        kirim_summa = math.floor(amount / rate)

    chiqim_str = f"{chiqim_summa:,}".replace(',', ' ')
    kirim_str  = f"{kirim_summa:,}".replace(',', ' ')
    izoh       = f"Ayirboshlash (Kurs: {rate:,})".replace(',', ' ')

    ok1, entry1 = save_kassa(uid, "Chiqim", chiqim_str, chiqim_val, izoh)
    ok2, entry2 = save_kassa(uid, "Kirim",  kirim_str,  kirim_val,  izoh)

    await state.clear()

    if ok1 and ok2:
        _last_saved[uid] = {
            "entries": [entry1, entry2],
            "time":    vaqt,
            "tur":     "Ayirboshlash",
            "summa":   f"{chiqim_str} {chiqim_val} 🔄 {kirim_str} {kirim_val}",
            "valyuta": "",
            "izoh":    izoh,
        }
        await message.answer(
            f"✅ <b>Ayirboshlash saqlandi!</b>\n\n"
            f"💸 Chiqim: <b>{chiqim_str} {chiqim_val}</b>\n"
            f"💰 Kirim:  <b>{kirim_str} {kirim_val}</b>\n"
            f"📝 {izoh}",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
        if ADMIN_CHAT_ID:
            try:
                uname = f"@{message.from_user.username}" if message.from_user.username else "—"
                await bot.send_message(
                    ADMIN_CHAT_ID,
                    f"🔄 <b>AYIRBOSHLASH</b>\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"💸 Chiqim: {chiqim_str} {chiqim_val}\n"
                    f"💰 Kirim:  {kirim_str} {kirim_val}\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"👤 {message.from_user.full_name} ({uname})\n"
                    f"🆔 <code>{uid}</code>\n"
                    f"🕐 {vaqt.strftime('%d.%m.%Y %H:%M')}",
                    parse_mode="HTML",
                )
            except Exception as e:
                logging.error(f"Admin ayirboshlash xabari yuborilmadi: {e}")
    else:
        await message.answer(
            "❌ Saqlashda xato yuz berdi. Qayta urinib ko'ring.",
            reply_markup=main_menu(),
        )


# ─── OXIRGINI BEKOR QILISH ────────────────────────────────────────────────────

@router.message(F.text == "↩️ Oxirgini bekor qilish")
async def undo_start(message: Message):
    uid  = message.from_user.id
    last = _last_saved.get(uid)

    if not last:
        await message.answer(
            "ℹ️ Bekor qilish uchun yozuv topilmadi.\n"
            "(Faqat joriy sessiyada kiritilgan yozuvni bekor qilish mumkin)",
            reply_markup=main_menu(),
        )
        return

    elapsed = (datetime.now() - last["time"]).total_seconds()
    if elapsed > UNDO_TTL:
        del _last_saved[uid]
        await message.answer(
            "⏰ Bekor qilish muddati tugagan (5 daqiqa).",
            reply_markup=main_menu(),
        )
        return

    tur   = last["tur"]
    summa = last["summa"]
    izoh  = last["izoh"]
    val   = last.get("valyuta", "")
    emoji = "🔄" if tur == "Ayirboshlash" else ("💰" if tur == "Kirim" else "💸")
    qoldi = int(UNDO_TTL - elapsed)

    await message.answer(
        f"⚠️ <b>Oxirgi yozuvni bekor qilasizmi?</b>\n\n"
        f"{emoji} {tur}: {summa} {val} — {izoh}\n\n"
        f"⏳ {qoldi} soniya qoldi",
        parse_mode="HTML",
        reply_markup=undo_keyboard(),
    )


@router.callback_query(F.data == "undo_yes")
async def cb_undo_yes(callback: CallbackQuery, bot: Bot):
    uid  = callback.from_user.id
    last = _last_saved.get(uid)

    if not last:
        await callback.answer("Yozuv topilmadi.", show_alert=True)
        return

    if (datetime.now() - last["time"]).total_seconds() > UNDO_TTL:
        del _last_saved[uid]
        await callback.answer("Muddat tugagan.", show_alert=True)
        return

    if "entries" in last:
        ok1 = delete_kassa_entry(last["entries"][0])
        ok2 = delete_kassa_entry(last["entries"][1])
        ok  = ok1 and ok2
    else:
        ok = delete_kassa_entry(last["entry"])

    tur   = last["tur"]
    summa = last["summa"]
    izoh  = last["izoh"]
    val   = last.get("valyuta", "")
    emoji = "🔄" if tur == "Ayirboshlash" else ("💰" if tur == "Kirim" else "💸")

    if ok:
        del _last_saved[uid]
        await callback.message.edit_text(
            f"✅ <b>Bekor qilindi!</b>\n\n{emoji} {tur}: {summa} {val} — {izoh}",
            parse_mode="HTML",
        )
        await callback.message.answer("Keyingi amalni tanlang:", reply_markup=main_menu())

        if ADMIN_CHAT_ID:
            try:
                u = callback.from_user
                await bot.send_message(
                    ADMIN_CHAT_ID,
                    f"🗑️ <b>BEKOR QILINDI</b>\n"
                    f"{emoji} {tur}: {summa} {val} — {izoh}\n"
                    f"👤 {u.full_name} (<code>{uid}</code>)",
                    parse_mode="HTML",
                )
            except Exception as e:
                logging.error(f"Admin bekor qilish xabari: {e}")
    else:
        await callback.message.edit_text("❌ O'chirishda xato. Sheets dan qo'lda o'chiring.")
        await callback.message.answer("Keyingi amalni tanlang:", reply_markup=main_menu())

    await callback.answer()


@router.callback_query(F.data == "undo_no")
async def cb_undo_no(callback: CallbackQuery):
    await callback.message.edit_text("ℹ️ Bekor qilish rad etildi.")
    await callback.message.answer("Keyingi amalni tanlang:", reply_markup=main_menu())
    await callback.answer()


# ─── BUGUNGI HISOBOT ──────────────────────────────────────────────────────────

def _build_hisobot(report: dict, today: str, full_name: str | None = None) -> str:
    """
    Foydalanuvchi yoki admin uchun kassa uslubidagi hisobot matni.
    full_name berilsa — foydalanuvchi nomi sarlavhaga qo'shiladi.
    """
    k_som = report["kirim_som"]
    k_usd = report["kirim_usd"]
    c_som = report["chiqim_som"]
    c_usd = report["chiqim_usd"]
    b_som = k_som - c_som
    b_usd = k_usd - c_usd

    # Yozuvlarni chiqim / kirim bo'lib ajratamiz
    chiqim_entries = [e for e in report.get("entries", []) if e["tur"].lower() == "chiqim"]
    kirim_entries  = [e for e in report.get("entries", []) if e["tur"].lower() == "kirim"]

    def jami_str(som: float, usd: float) -> str:
        parts = []
        if usd:  parts.append(f"<b>{_fmt(usd)} $</b>")
        if som:  parts.append(f"<b>{_fmt(som)} so'm</b>")
        return "  |  ".join(parts) if parts else "—"

    lines = ["💰 <b>KASSA</b>"]
    if full_name:
        lines.append(f"👤 {full_name}")
    lines += [
        "",
        "━━━━━━━━━━━━━",
        f"📅 {today}",
        "━━━━━━━━━━━━━",
    ]

    # ── CHIQIM ──
    if chiqim_entries:
        lines += [
            "",
            f"📤 <b>CHIQIM</b>",
            f"Jami: {jami_str(c_som, c_usd)}",
            "",
        ]
        for e in chiqim_entries:
            s = _fmt(_parse_amount(e['summa'])) if e['summa'] else e['summa']
            lines.append(f"▪️ Naqd / {s} {e['valyuta']} — {e['izoh']}")

    # ── KIRIM ──
    if kirim_entries:
        lines += [
            "",
            f"📥 <b>KIRIM</b>",
            f"Jami: {jami_str(k_som, k_usd)}",
            "",
        ]
        for e in kirim_entries:
            s = _fmt(_parse_amount(e['summa'])) if e['summa'] else e['summa']
            lines.append(f"▪️ Naqd / {s} {e['valyuta']} — {e['izoh']}")

    # ── BALANS ──
    if chiqim_entries or kirim_entries:
        balans_parts = []
        b_usd_sign = "+" if b_usd >= 0 else ""
        b_som_sign = "+" if b_som >= 0 else ""
        if k_usd or c_usd: balans_parts.append(f"<b>{b_usd_sign}{_fmt(b_usd)} $</b>")
        if k_som or c_som: balans_parts.append(f"<b>{b_som_sign}{_fmt(b_som)} so'm</b>")
        lines += [
            "",
            "━━━━━━━━━━━━━",
            f"💼 Balans: {'  |  '.join(balans_parts)}",
        ]
    else:
        lines.append("\n📭 Bugun hech qanday yozuv yo'q.")

    return "\n".join(lines)


@router.message(F.text == "📊 Bugungi hisobot")
async def hisobot_button(message: Message):
    msg = await message.answer("⏳ Yuklanmoqda...")
    uid = message.from_user.id
    report = get_today_report(telegram_id=uid)

    if not report:
        await msg.edit_text("❌ Hisobotni olishda xato.")
        return

    today = datetime.now().strftime("%d.%m.%Y")
    text = _build_hisobot(report, today)
    await msg.edit_text(text, parse_mode="HTML")


# ─── YAKUNIY HISOBOT ──────────────────────────────────────────────────────────

@router.message(F.text == "📋 Yakuniy hisobot")
async def overall_hisobot_button(message: Message):
    msg = await message.answer("⏳ Yuklanmoqda...")
    uid = message.from_user.id
    report = get_overall_report(telegram_id=uid)

    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    b_som = report.get("b_som", 0.0)
    b_usd = report.get("b_usd", 0.0)

    balans_parts = []
    if b_usd != 0:
        sign = "+" if b_usd >= 0 else ""
        balans_parts.append(f"<b>{sign}{_fmt(b_usd)} $</b>")
    sign = "+" if b_som >= 0 else ""
    balans_parts.append(f"<b>{sign}{_fmt(b_som)} so'm</b>")

    lines = [
        "💰 <b>KASSA</b>",
        f"👤 {message.from_user.full_name}",
        "",
        "━━━━━━━━━━━━━",
        f"📅 {now_str}",
        "━━━━━━━━━━━━━",
        "",
        "💼 <b>YAKUNIY QOLDIQ</b>",
        f"Balans: {'  |  '.join(balans_parts)}",
    ]

    await msg.edit_text("\n".join(lines), parse_mode="HTML")

