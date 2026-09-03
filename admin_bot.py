"""
admin_bot.py — Admin Campaign Management Handlers (Phase 17 + 18).

Only accessible by ADMIN_TELEGRAM_ID.
Handles: /admin command, Campaigns menu, Create/Activate/Close campaign flows,
         Pending Requests list with pagination, open request details, accept/reject.
"""

import logging
import re
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from config import ADMIN_TELEGRAM_ID
from database import (
    get_active_promo_codes,
    get_promo_code_by_id,
    get_campaign_by_id,
    get_active_campaign,
    get_campaigns,
    get_campaign_pending_count,
    get_campaign_remaining_slots,
    create_campaign,
    activate_campaign,
    close_campaign,
    can_accept_request,
    get_pending_requests,
    get_pending_requests_count,
    get_request_by_id,
    review_request,
    get_user_benefited_promo_codes,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Conversation States
# ─────────────────────────────────────────────────────────────
(
    ADMIN_MENU,
    ADMIN_CAMPAIGNS_MENU,
    ADMIN_SELECTING_PROMO,
    ADMIN_ENTERING_MAX,
    ADMIN_CONFIRM_CLOSE,
    ADMIN_REQUESTS_MENU,
    ADMIN_REQUEST_DETAIL,
) = range(7)

PAGE_SIZE = 10  # Requests per page


# ─────────────────────────────────────────────────────────────
# Security Guard
# ─────────────────────────────────────────────────────────────
def is_admin(user_id: int) -> bool:
    return ADMIN_TELEGRAM_ID is not None and user_id == ADMIN_TELEGRAM_ID


async def deny_unauthorized(update: Update) -> None:
    """Send an unauthorized rejection message."""
    text = "🚫 هذا الأمر مخصص للمشرف فقط."
    if update.message:
        await update.message.reply_text(text)
    elif update.callback_query:
        await update.callback_query.answer(text, show_alert=True)


# ─────────────────────────────────────────────────────────────
# Campaign Statistics Block
# ─────────────────────────────────────────────────────────────
def build_campaign_stats(camp: dict, pending: int, remaining: int) -> str:
    """Format a campaign statistics block for display to admin."""
    status_emoji = {
        "active": "🟢 مفتوحة",
        "closed": "🔴 مغلقة",
        "full": "🟡 ممتلئة",
        "completed": "✅ مكتملة",
    }.get(camp.get("status", ""), camp.get("status", ""))

    created = (camp.get("created_at") or "")[:10]
    closed = (camp.get("closed_at") or "")[:10]

    lines = [
        f"🆔 Campaign #{camp['id']}",
        f"🎟️ Promo Code: {camp['promo_code']}",
        f"📊 الحالة: {status_emoji}",
        f"👥 الحد الأقصى: {camp['max_requests']}",
        f"⏳ الطلبات المعلقة: {pending}",
        f"📈 الأماكن المتبقية: {remaining}",
        f"📅 تاريخ الإنشاء: {created}",
    ]
    if closed:
        lines.append(f"📅 تاريخ الإغلاق: {closed}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Main Admin Menu
# ─────────────────────────────────────────────────────────────
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: /admin command."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        await deny_unauthorized(update)
        return ConversationHandler.END

    context.user_data.clear()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Campaigns", callback_data="admin_menu_campaigns")],
        [InlineKeyboardButton("🎟️ Promo Codes", callback_data="admin_menu_promo")],
        [InlineKeyboardButton("📥 Pending Requests", callback_data="admin_menu_requests")],
    ])
    text = "🛠️ لوحة تحكم المشرف\n\nاختر ما تريد إدارته:"
    if update.message:
        await update.message.reply_text(text, reply_markup=keyboard)
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    return ADMIN_MENU


# ─────────────────────────────────────────────────────────────
# Campaigns Menu
# ─────────────────────────────────────────────────────────────
async def show_campaigns_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show campaigns overview and action buttons."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        await deny_unauthorized(update)
        return ConversationHandler.END

    query = update.callback_query
    if query:
        await query.answer()

    # Build campaign overview text
    active_camp = get_active_campaign()
    if active_camp:
        pending = get_campaign_pending_count(active_camp["id"])
        remaining = get_campaign_remaining_slots(active_camp["id"])
        stats_text = (
            "📊 الـ Campaign المفتوحة حالياً:\n\n"
            + build_campaign_stats(active_camp, pending, remaining)
        )
    else:
        # Show the most recent campaign if no active one
        all_camps = get_campaigns()
        if all_camps:
            recent = all_camps[0]
            pending = get_campaign_pending_count(recent["id"])
            remaining = get_campaign_remaining_slots(recent["id"])
            stats_text = (
                "📊 آخر Campaign:\n\n"
                + build_campaign_stats(recent, pending, remaining)
                + "\n\n⚠️ ما كاينة حتى Campaign مفتوحة حالياً."
            )
        else:
            stats_text = "📊 ما كاينة حتى Campaign حالياً."

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Create Campaign", callback_data="admin_camp_create")],
        [
            InlineKeyboardButton("🟢 Activate Campaign", callback_data="admin_camp_activate"),
            InlineKeyboardButton("🔴 Close Campaign", callback_data="admin_camp_close"),
        ],
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_menu_campaigns")],
        [InlineKeyboardButton("⬅️ Back", callback_data="admin_back_main")],
    ])

    text = f"🎯 إدارة الـ Campaigns\n\n{stats_text}"

    if query:
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
        except Exception:
            await query.message.reply_text(text, reply_markup=keyboard)
    elif update.message:
        await update.message.reply_text(text, reply_markup=keyboard)
    return ADMIN_CAMPAIGNS_MENU


# ─────────────────────────────────────────────────────────────
# Back to Main Menu
# ─────────────────────────────────────────────────────────────
async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Navigate back to main admin menu."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        await deny_unauthorized(update)
        return ConversationHandler.END
    return await admin_command(update, context)


# ─────────────────────────────────────────────────────────────
# Create Campaign Flow — Step 1: Select Promo Code
# ─────────────────────────────────────────────────────────────
async def start_create_campaign(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show active promo codes for selection."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        await deny_unauthorized(update)
        return ConversationHandler.END

    query = update.callback_query
    if query:
        await query.answer()

    active_promos = get_active_promo_codes()
    if not active_promos:
        text = "⚠️ ما كاينة حتى Promo Code نشطة.\nخاصك تضيف وتفعل Promo Code أولاً."
        if query:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="admin_menu_campaigns")]
            ]))
        else:
            await update.message.reply_text(text)
        return ADMIN_CAMPAIGNS_MENU

    buttons = [
        [InlineKeyboardButton(f"🎟️ {p['code']}", callback_data=f"admin_promo_select_{p['id']}")]
        for p in active_promos
    ]
    buttons.append([InlineKeyboardButton("⬅️ إلغاء", callback_data="admin_menu_campaigns")])

    text = "🎟️ اختر Promo Code للـ Campaign الجديدة:\n(فقط الـ Promo Codes النشطة معروضة)"
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    return ADMIN_SELECTING_PROMO


# ─────────────────────────────────────────────────────────────
# Create Campaign Flow — Step 2: Promo selected, ask max_requests
# ─────────────────────────────────────────────────────────────
async def promo_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle promo code selection, ask for max_requests."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        await deny_unauthorized(update)
        return ConversationHandler.END

    query = update.callback_query
    if not query:
        return ADMIN_SELECTING_PROMO
    await query.answer()

    match = re.match(r"^admin_promo_select_(\d+)$", query.data or "")
    if not match:
        await query.answer("بيانات غير صالحة.", show_alert=True)
        return ADMIN_SELECTING_PROMO

    promo_id = int(match.group(1))
    promo = get_promo_code_by_id(promo_id)
    if not promo or promo["active"] != 1:
        await query.edit_message_text(
            "❌ هاد الـ Promo Code مو نشط.\nأعد المحاولة.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="admin_camp_create")]
            ])
        )
        return ADMIN_SELECTING_PROMO

    context.user_data["new_camp_promo_id"] = promo_id
    context.user_data["new_camp_promo_code"] = promo["code"]

    await query.edit_message_text(
        f"🎟️ Promo Code المختارة: {promo['code']}\n\n"
        "شحال من شخص بغيتي فهاد Campaign؟\n"
        "(أكتب رقم صحيح، مثال: 15)"
    )
    return ADMIN_ENTERING_MAX


# ─────────────────────────────────────────────────────────────
# Create Campaign Flow — Step 3: Receive max_requests
# ─────────────────────────────────────────────────────────────
async def receive_max_requests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validate max_requests input and create campaign."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        await deny_unauthorized(update)
        return ConversationHandler.END

    if not update.message or not update.message.text:
        await update.message.reply_text("❌ خاصك تكتب رقم صحيح أكبر من صفر. مثال: 15")
        return ADMIN_ENTERING_MAX

    raw = update.message.text.strip()
    if not raw.isdigit() or int(raw) <= 0:
        await update.message.reply_text(
            "❌ قيمة غير صالحة.\n"
            "خاصك تكتب رقم صحيح أكبر من 0.\n"
            "مثال: 15"
        )
        return ADMIN_ENTERING_MAX

    max_requests = int(raw)
    promo_id = context.user_data.get("new_camp_promo_id")
    promo_code = context.user_data.get("new_camp_promo_code")

    if not promo_id or not promo_code:
        await update.message.reply_text("⚠️ انتهت الجلسة. أعد المحاولة من /admin")
        return ConversationHandler.END

    try:
        camp_id = create_campaign(
            promo_code=promo_id,
            max_requests=max_requests,
            status="closed"
        )
    except ValueError as e:
        await update.message.reply_text(f"❌ خطأ في الإنشاء: {e}")
        return ADMIN_CAMPAIGNS_MENU

    logger.info(f"Admin created campaign #{camp_id} for promo {promo_code}, max={max_requests}")

    context.user_data["last_created_camp_id"] = camp_id
    context.user_data.pop("new_camp_promo_id", None)
    context.user_data.pop("new_camp_promo_code", None)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 الرجوع لـ Campaigns", callback_data="admin_menu_campaigns")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="admin_back_main")],
    ])

    await update.message.reply_text(
        f"✅ تخلقات Campaign بنجاح.\n\n"
        f"🎟️ Promo Code: {promo_code}\n"
        f"👥 العدد المحدد: {max_requests}\n"
        f"🔴 الحالة: مغلقة\n\n"
        "خاصك تفتحها يدوياً باش يبدا البوت يستقبل الطلبات.",
        reply_markup=keyboard
    )
    return ADMIN_CAMPAIGNS_MENU


# ─────────────────────────────────────────────────────────────
# Activate Campaign
# ─────────────────────────────────────────────────────────────
async def admin_activate_campaign(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Activate the most recent closed campaign."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        await deny_unauthorized(update)
        return ConversationHandler.END

    query = update.callback_query
    if query:
        await query.answer()

    # Check no other campaign is currently active
    existing_active = get_active_campaign()
    if existing_active:
        text = (
            "⚠️ كاينة Campaign أخرى مفتوحة حالياً.\n"
            "سدها أولاً قبل ما تفتح هادي."
        )
        if query:
            await query.answer(text, show_alert=True)
        else:
            await update.message.reply_text(text)
        return ADMIN_CAMPAIGNS_MENU

    # Find the most recent closed campaign
    closed_camps = get_campaigns(status="closed")
    if not closed_camps:
        text = "⚠️ ما كاينة حتى Campaign مغلقة يمكن تفعيلها."
        if query:
            await query.answer(text, show_alert=True)
        else:
            await update.message.reply_text(text)
        return ADMIN_CAMPAIGNS_MENU

    target = closed_camps[0]  # most recent

    try:
        activate_campaign(target["id"])
    except ValueError as e:
        text = f"❌ فشل التفعيل: {e}"
        if query:
            await query.answer(text, show_alert=True)
        else:
            await update.message.reply_text(text)
        return ADMIN_CAMPAIGNS_MENU

    logger.info(f"Admin activated campaign #{target['id']}")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Campaigns", callback_data="admin_menu_campaigns")],
    ])
    text = (
        f"🟢 Campaign تفتحات بنجاح.\n\n"
        f"🎟️ Promo Code: {target['promo_code']}\n"
        f"🆔 Campaign #{target['id']}"
    )
    if query:
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
        except Exception:
            await query.message.reply_text(text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, reply_markup=keyboard)
    return ADMIN_CAMPAIGNS_MENU


# ─────────────────────────────────────────────────────────────
# Close Campaign — Step 1: Confirmation
# ─────────────────────────────────────────────────────────────
async def admin_close_campaign_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask admin to confirm closing the active campaign."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        await deny_unauthorized(update)
        return ConversationHandler.END

    query = update.callback_query
    if query:
        await query.answer()

    active_camp = get_active_campaign()
    if not active_camp:
        # Also check 'full' status campaign
        full_camps = get_campaigns(status="full")
        active_camp = full_camps[0] if full_camps else None

    if not active_camp:
        text = "⚠️ ما كاينة حتى Campaign مفتوحة أو ممتلئة لإغلاقها."
        if query:
            await query.answer(text, show_alert=True)
        else:
            await update.message.reply_text(text)
        return ADMIN_CAMPAIGNS_MENU

    context.user_data["close_camp_id"] = active_camp["id"]
    pending = get_campaign_pending_count(active_camp["id"])

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ نعم، سدها", callback_data=f"admin_camp_close_confirm_{active_camp['id']}"),
            InlineKeyboardButton("❌ إلغاء", callback_data="admin_menu_campaigns"),
        ]
    ])
    text = (
        f"⚠️ واش متأكد بغيتي تسد هاد Campaign؟\n\n"
        f"🎟️ Promo Code: {active_camp['promo_code']}\n"
        f"🆔 Campaign #{active_camp['id']}\n"
        f"⏳ الطلبات المعلقة: {pending}\n\n"
        "الطلبات الموجودة مش غادي تحذف. فقط غادي تتوقف الطلبات الجديدة."
    )
    if query:
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
        except Exception:
            await query.message.reply_text(text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, reply_markup=keyboard)
    return ADMIN_CONFIRM_CLOSE


# ─────────────────────────────────────────────────────────────
# Close Campaign — Step 2: Execute Close
# ─────────────────────────────────────────────────────────────
async def admin_close_campaign_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Execute campaign close after admin confirmation."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        await deny_unauthorized(update)
        return ConversationHandler.END

    query = update.callback_query
    if not query:
        return ADMIN_CAMPAIGNS_MENU
    await query.answer()

    match = re.match(r"^admin_camp_close_confirm_(\d+)$", query.data or "")
    if not match:
        await query.answer("بيانات غير صالحة.", show_alert=True)
        return ADMIN_CAMPAIGNS_MENU

    camp_id = int(match.group(1))
    camp = get_campaign_by_id(camp_id)
    if not camp:
        await query.answer("Campaign غير موجودة.", show_alert=True)
        return ADMIN_CAMPAIGNS_MENU

    # Safety: if already closed/completed, just show info
    if camp["status"] in ("closed", "completed"):
        await query.answer("هاد الـ Campaign مغلقة مسبقاً.", show_alert=True)
        return await show_campaigns_menu(update, context)

    close_campaign(camp_id)
    logger.info(f"Admin closed campaign #{camp_id}")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Campaigns", callback_data="admin_menu_campaigns")],
    ])
    text = (
        f"🔴 Campaign تسدات بنجاح.\n\n"
        f"🎟️ Promo Code: {camp['promo_code']}\n"
        f"🆔 Campaign #{camp_id}\n\n"
        "البوت مش غادي يستقبل طلبات جديدة لهاد العرض."
    )
    try:
        await query.edit_message_text(text, reply_markup=keyboard)
    except Exception:
        await query.message.reply_text(text, reply_markup=keyboard)
    return ADMIN_CAMPAIGNS_MENU


# ─────────────────────────────────────────────────────────────
# Placeholder handler for Promo Codes (future phase)
# ─────────────────────────────────────────────────────────────
async def admin_promo_placeholder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user or not is_admin(user.id):
        await deny_unauthorized(update)
        return ConversationHandler.END
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "🎟️ إدارة Promo Codes — قريباً في مرحلة قادمة.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="admin_back_main")]
            ])
        )
    return ADMIN_MENU


# ─────────────────────────────────────────────────────────────
# Pending Requests — List with Pagination
# ─────────────────────────────────────────────────────────────
async def show_pending_requests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display paginated list of pending requests."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        await deny_unauthorized(update)
        return ConversationHandler.END

    query = update.callback_query
    if query:
        await query.answer()

    # Determine current page from context or default to 0
    page = context.user_data.get("requests_page", 0)
    total = get_pending_requests_count()
    requests = get_pending_requests(limit=PAGE_SIZE, offset=page * PAGE_SIZE)

    if total == 0:
        text = "📭 ما كاين حتى طلب قيد المراجعة حالياً."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="admin_requests_refresh")],
            [InlineKeyboardButton("⬅️ Back", callback_data="admin_back_main")],
        ])
        if query:
            try:
                await query.edit_message_text(text, reply_markup=keyboard)
            except Exception:
                await query.message.reply_text(text, reply_markup=keyboard)
        elif update.message:
            await update.message.reply_text(text, reply_markup=keyboard)
        return ADMIN_REQUESTS_MENU

    # Build list message
    lines = [f"📥 الطلبات المعلقة ({total} طلب) — صفحة {page + 1}\n"]
    buttons = []
    for req in requests:
        created = (req.get("created_at") or "")[:10]
        username_str = f"@{req['username']}" if req.get("username") else "-"
        lines.append(
            f"📥 طلب #{req['id']}\n"
            f"  🎟️ {req['promo_code']}  🆔 {req['site_id']}\n"
            f"  👤 {req.get('first_name', '-')} ({username_str})  📅 {created}"
        )
        buttons.append([
            InlineKeyboardButton(
                f"📄 فتح الطلب #{req['id']}",
                callback_data=f"admin_req_open_{req['id']}"
            )
        ])

    # Pagination nav buttons
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"admin_req_page_{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("➡️ التالي", callback_data=f"admin_req_page_{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("🔄 تحديث", callback_data="admin_requests_refresh")])
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="admin_back_main")])

    text = "\n\n".join(lines)
    keyboard = InlineKeyboardMarkup(buttons)

    if query:
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
        except Exception:
            await query.message.reply_text(text, reply_markup=keyboard)
    elif update.message:
        await update.message.reply_text(text, reply_markup=keyboard)
    return ADMIN_REQUESTS_MENU


async def requests_page_nav(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle page navigation for the pending requests list."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        await deny_unauthorized(update)
        return ConversationHandler.END

    query = update.callback_query
    if not query:
        return ADMIN_REQUESTS_MENU
    await query.answer()

    match = re.match(r"^admin_req_page_(\d+)$", query.data or "")
    if match:
        context.user_data["requests_page"] = int(match.group(1))
    return await show_pending_requests(update, context)


async def requests_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Refresh the pending requests list (reset to page 0)."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        await deny_unauthorized(update)
        return ConversationHandler.END
    context.user_data["requests_page"] = 0
    return await show_pending_requests(update, context)


# ─────────────────────────────────────────────────────────────
# Pending Requests — Open Request Detail
# ─────────────────────────────────────────────────────────────
async def open_request_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show full details of a single pending request including screenshot."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        await deny_unauthorized(update)
        return ConversationHandler.END

    query = update.callback_query
    if not query:
        return ADMIN_REQUESTS_MENU
    await query.answer()

    match = re.match(r"^admin_req_open_(\d+)$", query.data or "")
    if not match:
        await query.answer("بيانات غير صالحة.", show_alert=True)
        return ADMIN_REQUESTS_MENU

    req_id = int(match.group(1))
    req = get_request_by_id(req_id)

    if not req:
        await query.answer("الطلب غير موجود.", show_alert=True)
        return ADMIN_REQUESTS_MENU

    # Stale request protection
    if req["status"] != "pending":
        status_labels = {
            "accepted": "مقبول ✅",
            "rejected": "مرفوض ❌",
            "approved": "معتمد ✅",
        }
        label = status_labels.get(req["status"], req["status"])
        await query.answer(
            f"⚠️ هاد الطلب تمت معالجته من قبل. الحالة: {label}",
            show_alert=True
        )
        # Reset to list
        context.user_data["requests_page"] = 0
        return await show_pending_requests(update, context)

    username_str = f"@{req['username']}" if req.get("username") else "-"
    created = (req.get("created_at") or "")[:19].replace("T", " ")
    detail_text = (
        f"📥 طلب قيد المراجعة #{req_id}\n\n"
        f"🎟️ Promo Code: {req['promo_code']}\n"
        f"🆔 Site ID: {req['site_id']}\n"
        f"🔗 Telegram User ID: {req['telegram_user_id']}\n"
        f"👤 Username: {username_str}\n"
        f"👤 First Name: {req.get('first_name', '-')}\n"
        f"📅 Created At: {created}\n"
        f"⏳ Status: PENDING"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ قبول الطلب", callback_data=f"admin_req_accept_{req_id}"),
            InlineKeyboardButton("❌ رفض الطلب", callback_data=f"admin_req_reject_{req_id}"),
        ],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="admin_menu_requests")],
    ])

    screenshot = req.get("screenshot_file_id")
    if screenshot:
        try:
            await query.message.reply_photo(
                photo=screenshot,
                caption=detail_text,
                reply_markup=keyboard,
            )
            # Try to remove the original list message to keep chat clean
            try:
                await query.delete_message()
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Could not send screenshot for request #{req_id}: {e}")
            await query.edit_message_text(detail_text, reply_markup=keyboard)
    else:
        try:
            await query.edit_message_text(detail_text, reply_markup=keyboard)
        except Exception:
            await query.message.reply_text(detail_text, reply_markup=keyboard)

    return ADMIN_REQUEST_DETAIL


# ─────────────────────────────────────────────────────────────
# Pending Requests — Accept / Reject (reuses Phase 16 logic)
# ─────────────────────────────────────────────────────────────
async def request_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle accept or reject action on a pending request from the detail view."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        await deny_unauthorized(update)
        return ConversationHandler.END

    query = update.callback_query
    if not query:
        return ADMIN_REQUEST_DETAIL
    await query.answer()

    match = re.match(r"^admin_req_(accept|reject)_(\d+)$", query.data or "")
    if not match:
        await query.answer("بيانات غير صالحة.", show_alert=True)
        return ADMIN_REQUEST_DETAIL

    action, req_id_str = match.group(1), match.group(2)
    req_id = int(req_id_str)
    target_status = "accepted" if action == "accept" else "rejected"

    # Reuse Phase 16 review_request() atomically
    success, reason = review_request(req_id, target_status)

    if not success:
        await query.answer(f"⚠️ {reason}", show_alert=True)
        # If stale, go back to list
        context.user_data["requests_page"] = 0
        return await show_pending_requests(update, context)

    # Fetch updated request for customer notification
    req = get_request_by_id(req_id)
    action_label = "✅ تم القبول" if action == "accept" else "❌ تم الرفض"

    # Update admin message
    try:
        if query.message and query.message.photo:
            new_caption = f"{query.message.caption or ''}\n\n📌 النتيجة: {action_label}"
            await query.edit_message_caption(caption=new_caption, reply_markup=None)
        elif query.message:
            new_text = f"{query.message.text or ''}\n\n📌 النتيجة: {action_label}"
            await query.edit_message_text(text=new_text, reply_markup=None)
    except Exception as e:
        logger.warning(f"Could not update admin message for request #{req_id}: {e}")

    # Notify customer
    if req:
        customer_tg_id = req.get("telegram_user_id")
        promo_code = req.get("promo_code", "")
        site_id = req.get("site_id", "")
        if action == "accept":
            customer_msg = (
                "🎉 تم قبول الطلب ديالك بنجاح!\n\n"
                f"🎟️ Promo Code: {promo_code}\n"
                f"🆔 Site ID: {site_id}\n\n"
                "شكراً لمشاركتك معنا! ✅"
            )
        else:
            benefited_codes = get_user_benefited_promo_codes(req["user_id"])
            if benefited_codes:
                codes_list_str = "\n".join(f"• {code}" for code in benefited_codes)
                customer_msg = (
                    "❌ الطلب ديالك ترفض.\n\n"
                    "📌 الأكواد اللي سبق ليك استفدتي منهم:\n"
                    f"{codes_list_str}"
                )
            else:
                customer_msg = (
                    "❌ الطلب ديالك ترفض.\n\n"
                    "📌 ما سبقش ليك استفدتي من حتى كود."
                )
        try:
            await context.bot.send_message(chat_id=customer_tg_id, text=customer_msg)
        except Exception as e:
            logger.warning(f"Could not notify customer {customer_tg_id}: {e}")

    logger.info(f"Admin {action}ed request #{req_id} from Pending Requests menu")

    # Return to refreshed list
    context.user_data["requests_page"] = 0
    return await show_pending_requests(update, context)


# ─────────────────────────────────────────────────────────────
# Build and return the ConversationHandler
# ─────────────────────────────────────────────────────────────
def build_admin_conversation_handler() -> ConversationHandler:
    """Construct the admin ConversationHandler to be registered in bot.py."""
    return ConversationHandler(
        entry_points=[CommandHandler("admin", admin_command)],
        states={
            ADMIN_MENU: [
                CallbackQueryHandler(show_campaigns_menu, pattern="^admin_menu_campaigns$"),
                CallbackQueryHandler(admin_promo_placeholder, pattern="^admin_menu_promo$"),
                CallbackQueryHandler(show_pending_requests, pattern="^admin_menu_requests$"),
                CallbackQueryHandler(back_to_main, pattern="^admin_back_main$"),
            ],
            ADMIN_CAMPAIGNS_MENU: [
                CallbackQueryHandler(start_create_campaign, pattern="^admin_camp_create$"),
                CallbackQueryHandler(admin_activate_campaign, pattern="^admin_camp_activate$"),
                CallbackQueryHandler(admin_close_campaign_confirm, pattern="^admin_camp_close$"),
                CallbackQueryHandler(show_campaigns_menu, pattern="^admin_menu_campaigns$"),
                CallbackQueryHandler(back_to_main, pattern="^admin_back_main$"),
            ],
            ADMIN_SELECTING_PROMO: [
                CallbackQueryHandler(promo_selected, pattern=r"^admin_promo_select_\d+$"),
                CallbackQueryHandler(show_campaigns_menu, pattern="^admin_menu_campaigns$"),
                CallbackQueryHandler(back_to_main, pattern="^admin_back_main$"),
            ],
            ADMIN_ENTERING_MAX: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_max_requests),
                CallbackQueryHandler(show_campaigns_menu, pattern="^admin_menu_campaigns$"),
            ],
            ADMIN_CONFIRM_CLOSE: [
                CallbackQueryHandler(
                    admin_close_campaign_execute,
                    pattern=r"^admin_camp_close_confirm_\d+$"
                ),
                CallbackQueryHandler(show_campaigns_menu, pattern="^admin_menu_campaigns$"),
                CallbackQueryHandler(back_to_main, pattern="^admin_back_main$"),
            ],
            ADMIN_REQUESTS_MENU: [
                CallbackQueryHandler(open_request_detail, pattern=r"^admin_req_open_\d+$"),
                CallbackQueryHandler(requests_page_nav, pattern=r"^admin_req_page_\d+$"),
                CallbackQueryHandler(requests_refresh, pattern="^admin_requests_refresh$"),
                CallbackQueryHandler(show_pending_requests, pattern="^admin_menu_requests$"),
                CallbackQueryHandler(back_to_main, pattern="^admin_back_main$"),
            ],
            ADMIN_REQUEST_DETAIL: [
                CallbackQueryHandler(request_action, pattern=r"^admin_req_(accept|reject)_\d+$"),
                CallbackQueryHandler(show_pending_requests, pattern="^admin_menu_requests$"),
                CallbackQueryHandler(back_to_main, pattern="^admin_back_main$"),
            ],
        },
        fallbacks=[
            CommandHandler("admin", admin_command),
        ],
        allow_reentry=True,
        per_message=False,
        name="admin_conversation",
    )
