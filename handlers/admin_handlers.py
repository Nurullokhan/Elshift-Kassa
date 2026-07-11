import logging
from datetime import datetime

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from services.google_sheets import is_admin_user, get_today_report, get_last_entries, _parse_amount

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

    chiqim_entries = [e for e in report.get("entries", []) if e["tur"].lower() == "chiqim"]
    kirim_entries  = [e for e in report.get("entries", []) if e["tur"].lower() == "kirim"]

    def jami_str(som: float, usd: float) -> str:
        parts = []
        if usd: parts.append(f"<b>{_fmt(usd)} $</b>")
        if som: parts.append(f"<b>{_fmt(som)} so'm</b>")
        return "  |  ".join(parts) if parts else "—"

    lines = [
        "💰 <b>KASSA</b>",
        "🔑 Barchasi (Admin)",
        "",
        "━━━━━━━━━━━━━",
        f"📅 {today}",
        "━━━━━━━━━━━━━",
    ]

    if chiqim_entries:
        lines += ["", "📤 <b>CHIQIM</b>", f"Jami: {jami_str(c_som, c_usd)}", ""]
        for e in chiqim_entries:
            s = _fmt(_parse_amount(e['summa'])) if e['summa'] else e['summa']
            lines.append(f"▪️ Naqd / {s} {e['valyuta']} — {e['izoh']}")

    if kirim_entries:
        lines += ["", "📥 <b>KIRIM</b>", f"Jami: {jami_str(k_som, k_usd)}", ""]
        for e in kirim_entries:
            s = _fmt(_parse_amount(e['summa'])) if e['summa'] else e['summa']
            lines.append(f"▪️ Naqd / {s} {e['valyuta']} — {e['izoh']}")

    if chiqim_entries or kirim_entries:
        balans_parts = []
        if k_usd or c_usd:
            sign = "+" if b_usd >= 0 else ""
            balans_parts.append(f"<b>{sign}{_fmt(b_usd)} $</b>")
        sign = "+" if b_som >= 0 else ""
        balans_parts.append(f"<b>{sign}{_fmt(b_som)} so'm</b>")
        lines += ["", "━━━━━━━━━━━━━", f"💼 Balans: {'  |  '.join(balans_parts)}"]
    else:
        lines.append("\n📭 Bugun hech qanday yozuv yo'q.")

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
        s = _fmt(_parse_amount(e['summa'])) if e['summa'] else e['summa']
        lines.append(f"{emoji} {e['vaqt']} | <b>{s} {val}</b> | {e['izoh']}")

    await msg.edit_text("\n".join(lines), parse_mode="HTML")
