import logging
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from config import ADMIN_CHAT_ID
from keyboards.kassa_keyboards import main_menu, cancel_keyboard, undo_keyboard
from states.kassa_states import KassaState
from services.google_sheets import is_allowed_user, save_kassa, delete_kassa_entry, get_today_report

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
    # Ajratuvchi: boʻsh joy bilan ' - ' (afzal), yoki shunchaki '-'
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
        await message.answer(
            "❌ <b>Sizda bu botdan foydalanish huquqi yo'q.</b>\n\n"
            "Qo'shilish uchun admin bilan bog'laning.",
            parse_mode="HTML",
        )
        return
    await message.answer(
        f"👋 Salom, <b>{name}</b>!\n\n"
        f"<b>Elshift Kassa</b>\n\n"
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
    await message.answer(
        "💰 <b>Kirim</b>\n\n"
        "Izoh va summani <b>-</b> bilan ajratib yozing:\n\n"
        "<code>Alukabond shopiriga - 1.005.000</code>\n"
        "<code>Zuhriddinga - 500$</code>\n"
        "<code>1500000 - Ish haqi</code>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )


@router.message(F.text == "💸 Chiqim")
async def chiqim_start(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(tur="Chiqim")
    await state.set_state(KassaState.input)
    await message.answer(
        "💸 <b>Chiqim</b>\n\n"
        "Izoh va summani <b>-</b> bilan ajratib yozing:\n\n"
        "<code>Elektr to'lovi - 250.000</code>\n"
        "<code>Material xaridi - 1,500,000</code>\n"
        "<code>800000 - Ishchi maoshi</code>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )


# ─── KIRITISH ─────────────────────────────────────────────────────────────────

@router.message(KassaState.input)
async def kassa_input(message: Message, state: FSMContext, bot: Bot):
    text = message.text.strip()

    if text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=main_menu())
        return

    summa, valyuta, izoh = _parse_input(text)

    if summa is None:
        await message.answer(
            "⚠️ Format noto'g'ri. Namunalar:\n\n"
            "<code>Alukabond shopiriga - 1.005.000</code>\n"
            "<code>500$ - Zuhriddinga</code>\n"
            "<code>1500000 - Ish haqi</code>\n\n"
            "Izoh va summani <b> - </b> bilan ajrating.",
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    tur  = data["tur"]
    uid  = message.from_user.id

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
    emoji = "💰" if tur == "Kirim" else "💸"
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

    ok    = delete_kassa_entry(last["entry"])
    tur   = last["tur"]
    summa = last["summa"]
    izoh  = last["izoh"]
    val   = last.get("valyuta", "")
    emoji = "💰" if tur == "Kirim" else "💸"

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
                logging.error(f"Admin xabari: {e}")
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

@router.message(F.text == "📊 Bugungi hisobot")
async def hisobot_button(message: Message):
    msg = await message.answer("⏳ Yuklanmoqda...")
    report = get_today_report()

    if not report:
        await msg.edit_text("❌ Hisobotni olishda xato.")
        return

    today = datetime.now().strftime("%d.%m.%Y")
    k_som = report["kirim_som"]
    k_usd = report["kirim_usd"]
    c_som = report["chiqim_som"]
    c_usd = report["chiqim_usd"]
    b_som = k_som - c_som
    b_usd = k_usd - c_usd

    lines = [
        f"📊 <b>BUGUNGI HISOBOT — {today}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💰 <b>KIRIM</b> ({report['kirim_count']} ta yozuv)",
    ]
    if k_som: lines.append(f"   So'm:   <b>{_fmt(k_som)} so'm</b>")
    if k_usd: lines.append(f"   Dollar: <b>{_fmt(k_usd)} $</b>")
    if not k_som and not k_usd: lines.append("   — yo'q")

    lines.append(f"\n💸 <b>CHIQIM</b> ({report['chiqim_count']} ta yozuv)")
    if c_som: lines.append(f"   So'm:   <b>{_fmt(c_som)} so'm</b>")
    if c_usd: lines.append(f"   Dollar: <b>{_fmt(c_usd)} $</b>")
    if not c_som and not c_usd: lines.append("   — yo'q")

    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━",
        "💼 <b>BALANS:</b>",
        f"   So'm:   <b>{'+' if b_som >= 0 else ''}{_fmt(b_som)} so'm</b>",
    ]
    if k_usd or c_usd:
        lines.append(f"   Dollar: <b>{'+' if b_usd >= 0 else ''}{_fmt(b_usd)} $</b>")

    await msg.edit_text("\n".join(lines), parse_mode="HTML")
