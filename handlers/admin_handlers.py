import logging
from datetime import datetime

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from services.google_sheets import is_admin_user, get_today_report, get_last_entries

router = Router()


def _fmt(n: float) -> str:
    return f"{int(n):,}".replace(",", " ")


def _hisobot_text(report: dict) -> str:
    today  = datetime.now().strftime("%d.%m.%Y")
    k_som  = report.get("kirim_som", 0)
    k_usd  = report.get("kirim_usd", 0)
    c_som  = report.get("chiqim_som", 0)
    c_usd  = report.get("chiqim_usd", 0)
    b_som  = k_som - c_som
    b_usd  = k_usd - c_usd

    lines = [
        f"📊 <b>BUGUNGI HISOBOT (BARCHASI) — {today}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💰 <b>KIRIM</b> ({report.get('kirim_count', 0)} ta)",
    ]
    if k_som: lines.append(f"   So'm:   <b>{_fmt(k_som)} so'm</b>")
    if k_usd: lines.append(f"   Dollar: <b>{_fmt(k_usd)} $</b>")
    if not k_som and not k_usd: lines.append("   — yo'q")

    lines.append(f"\n💸 <b>CHIQIM</b> ({report.get('chiqim_count', 0)} ta)")
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

    # Yozuvlar ro'yxati (admin uchun)
    entries = report.get("entries", [])
    if entries:
        lines.append("\n📋 <b>Barcha yozuvlar:</b>")
        for e in entries:
            emoji = "💰" if e["tur"].lower() == "kirim" else "💸"
            vaqt_soat = e["vaqt"][11:] if len(e["vaqt"]) > 11 else e["vaqt"]
            val = e.get("valyuta", "")
            lines.append(f"  {emoji} {vaqt_soat} | <b>{e['summa']} {val}</b> | {e['izoh']}")

    return "\n".join(lines)


# ─── /hisobot ─────────────────────────────────────────────────────────────────

@router.message(Command("hisobot"))
async def cmd_hisobot(message: Message):
    if not is_admin_user(message.from_user.id):
        await message.answer("❌ Bu buyruq faqat adminlar uchun.")
        return

    msg = await message.answer("⏳ Hisobot tayyorlanmoqda...")
    # Admin barcha foydalanuvchilar hisobotini ko'radi (telegram_id=None)
    report = get_today_report(telegram_id=None)
    if not report:
        await msg.edit_text("❌ Hisobotni olishda xato yuz berdi.")
        return
    await msg.edit_text(_hisobot_text(report), parse_mode="HTML")


# ─── /balans ──────────────────────────────────────────────────────────────────

@router.message(Command("balans"))
async def cmd_balans(message: Message):
    if not is_admin_user(message.from_user.id):
        await message.answer("❌ Bu buyruq faqat adminlar uchun.")
        return

    msg = await message.answer("⏳ Hisoblanmoqda...")
    # Admin barcha foydalanuvchilar balansini ko'radi (telegram_id=None)
    report = get_today_report(telegram_id=None)
    if not report:
        await msg.edit_text("❌ Ma'lumotni olishda xato.")
        return

    today = datetime.now().strftime("%d.%m.%Y")
    b_som = report.get("kirim_som", 0) - report.get("chiqim_som", 0)
    b_usd = report.get("kirim_usd", 0) - report.get("chiqim_usd", 0)
    k_usd = report.get("kirim_usd", 0)
    c_usd = report.get("chiqim_usd", 0)

    lines = [
        f"💼 <b>BALANS (BARCHASI) — {today}</b>",
        "━━━━━━━━━━━━━━━━",
        f"So'm:   <b>{'+' if b_som >= 0 else ''}{_fmt(b_som)} so'm</b>",
    ]
    if k_usd or c_usd:
        lines.append(f"Dollar: <b>{'+' if b_usd >= 0 else ''}{_fmt(b_usd)} $</b>")

    await msg.edit_text("\n".join(lines), parse_mode="HTML")


# ─── /oxirgi [N] ──────────────────────────────────────────────────────────────

@router.message(Command("oxirgi"))
async def cmd_oxirgi(message: Message):
    if not is_admin_user(message.from_user.id):
        await message.answer("❌ Bu buyruq faqat adminlar uchun.")
        return

    parts = message.text.split() if message.text else []
    n = 10
    if len(parts) > 1:
        try:
            n = max(1, min(int(parts[1]), 50))
        except ValueError:
            pass

    msg = await message.answer(f"⏳ Oxirgi {n} ta yozuv olinmoqda...")
    entries = get_last_entries(n)

    if not entries:
        await msg.edit_text("ℹ️ Hozircha yozuvlar yo'q.")
        return

    lines = [f"📋 <b>Oxirgi {n} ta yozuv:</b>", "━━━━━━━━━━━━━━━━"]
    for e in entries:
        emoji = "💰" if e["tur"].lower() == "kirim" else "💸"
        val = e.get("valyuta", "")
        lines.append(f"{emoji} {e['vaqt']} | <b>{e['summa']} {val}</b> | {e['izoh']}")

    await msg.edit_text("\n".join(lines), parse_mode="HTML")
