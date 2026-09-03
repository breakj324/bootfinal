import logging
import re
from pathlib import Path
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from config import BOT_TOKEN, ADMIN_TELEGRAM_ID
from database import (
    initialize_database,
    create_or_update_user,
    get_user_by_telegram_id,
    get_active_campaign,
    can_accept_request,
    has_user_benefited,
    has_user_pending_request,
    get_user_benefited_promo_codes,
    create_request,
    get_request_by_id,
    review_request,
)
from admin_bot import build_admin_conversation_handler

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation States
WAITING_FOR_SCREENSHOT, WAITING_FOR_SITE_ID = range(2)


def normalize_site_id(text: Optional[str]) -> Optional[str]:
    """
    Normalize and validate customer-provided Site ID.
    Accepts formats such as:
    - ID:38938378
    - ID: 38938378
    - 38938378
    - id: 38938378
    """
    if not text:
        return None
    raw = text.strip()
    match = re.match(r"^(?:id\s*:\s*)?([a-zA-Z0-9_-]{3,50})$", raw, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /start command, register user, check campaign availability, and show offer."""
    context.user_data.clear()

    user = update.effective_user
    if not user:
        return ConversationHandler.END

    telegram_user_id = user.id
    username = user.username
    first_name = user.first_name

    # 1. Register or update Telegram user
    db_user_id = create_or_update_user(
        telegram_user_id=telegram_user_id,
        username=username,
        first_name=first_name,
    )
    context.user_data["db_user_id"] = db_user_id
    context.user_data["telegram_user_id"] = telegram_user_id

    logger.info(
        f"/start - DB ID: {db_user_id}, Telegram User ID: {telegram_user_id}, "
        f"Username: {username}, First Name: {first_name}"
    )

    # 2. Check whether there is an active campaign available
    active_campaign = get_active_campaign()

    # 3. If no active campaign or campaign is full / cannot accept requests
    if not active_campaign or not can_accept_request(active_campaign["id"]):
        no_campaign_msg = (
            "حالياً ما كاين حتى عرض مفتوح.\n"
            "تابع القناة باش تعرف ملي يفتح عرض جديد."
        )
        if update.message:
            await update.message.reply_text(no_campaign_msg)
        elif update.callback_query:
            await update.callback_query.message.reply_text(no_campaign_msg)
        return ConversationHandler.END

    # Check whether this user has already benefited from this promo code
    promo_code_id = active_campaign["promo_code_id"]
    if has_user_benefited(db_user_id, promo_code_id):
        already_benefited_msg = (
            "❌ سبق ليك استفدتي من هاد Promo Code.\n"
            "كل شخص يقدر يستافد من هاد الكود مرة وحدة."
        )
        if update.message:
            await update.message.reply_text(already_benefited_msg)
        elif update.callback_query:
            await update.callback_query.message.reply_text(already_benefited_msg)
        return ConversationHandler.END

    # Check whether this user already has a pending request in this campaign
    if has_user_pending_request(db_user_id, active_campaign["id"]):
        already_pending_msg = (
            "⏳ عندك طلب قيد المراجعة فهاد العرض.\n"
            "غادي يتم التواصل معاك قريباً."
        )
        if update.message:
            await update.message.reply_text(already_pending_msg)
        elif update.callback_query:
            await update.callback_query.message.reply_text(already_pending_msg)
        return ConversationHandler.END

    # Store campaign in session state
    context.user_data["campaign_id"] = active_campaign["id"]
    context.user_data["promo_code"] = active_campaign["promo_code"]
    context.user_data["promo_code_id"] = promo_code_id

    promo_code = active_campaign["promo_code"]
    desc = active_campaign.get("promo_description") or ""
    instr = active_campaign.get("promo_instructions") or ""
    reqs = active_campaign.get("promo_requirements") or ""
    example_image = active_campaign.get("promo_example_image")

    offer_text = (
        f"🎁 العرض متاح\n\n"
        f"🎟️ Promo Code:\n"
        f"{promo_code}\n\n"
    )
    if desc:
        offer_text += f"📝 الوصف:\n{desc}\n\n"
    if instr:
        offer_text += f"📋 الخطوات:\n{instr}\n\n"
    if reqs:
        offer_text += f"⚠️ الشروط:\n{reqs}\n"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ فهمت، نبدأ", callback_data="start_submission")]
    ])

    sent_with_photo = False
    if example_image:
        if Path(example_image).is_file():
            try:
                with open(example_image, "rb") as photo_file:
                    if update.message:
                        await update.message.reply_photo(
                            photo=photo_file,
                            caption=offer_text,
                            reply_markup=keyboard,
                        )
                    elif update.callback_query:
                        await update.callback_query.message.reply_photo(
                            photo=photo_file,
                            caption=offer_text,
                            reply_markup=keyboard,
                        )
                sent_with_photo = True
            except Exception as e:
                logger.warning(f"Could not send local photo {example_image}: {e}")
        else:
            try:
                if update.message:
                    await update.message.reply_photo(
                        photo=example_image,
                        caption=offer_text,
                        reply_markup=keyboard,
                    )
                elif update.callback_query:
                    await update.callback_query.message.reply_photo(
                        photo=example_image,
                        caption=offer_text,
                        reply_markup=keyboard,
                    )
                sent_with_photo = True
            except Exception as e:
                logger.warning(f"Could not send photo {example_image}: {e}")

    if not sent_with_photo:
        if update.message:
            await update.message.reply_text(offer_text, reply_markup=keyboard)
        elif update.callback_query:
            await update.callback_query.message.reply_text(offer_text, reply_markup=keyboard)

    return WAITING_FOR_SCREENSHOT


async def handle_start_submission(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Triggered when customer clicks '✅ فهمت، نبدأ' button."""
    instruction_text = (
        "⚠️ ATTENTION\n\n"
        "خاص الحساب ضروري يكون تصوب هاد النهار، وما يكونش حساب قديم."
    )
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.reply_text(instruction_text)
    elif update.message:
        await update.message.reply_text(instruction_text)
    return WAITING_FOR_SCREENSHOT


async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the Telegram photo or video file_id and ask for Site ID."""
    if not update.message:
        return WAITING_FOR_SCREENSHOT

    file_id = None
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.video:
        file_id = update.message.video.file_id

    if not file_id:
        await update.message.reply_text("📸 أو 🎥 صيفط Screenshot أو Video ديال الإثبات.")
        return WAITING_FOR_SCREENSHOT

    context.user_data["screenshot_file_id"] = file_id

    await update.message.reply_text(
        "🆔 دابا صيفط Site ID ديالك مكتوب.\n"
        "مثال:\n"
        "ID:38938378"
    )
    return WAITING_FOR_SITE_ID


async def handle_unexpected_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle non-photo/non-video messages while waiting for media proof."""
    if update.message:
        await update.message.reply_text("📸 أو 🎥 صيفط Screenshot أو Video ديال الإثبات.")
    return WAITING_FOR_SCREENSHOT


async def handle_site_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validate Site ID, create pending request in database, notify admin, and display confirmation."""
    if not update.message or not update.message.text:
        await update.message.reply_text(
            "❌ ما قدرتش نقرأ الـID.\n"
            "صيفطو بهذا الشكل:\n"
            "ID:38938378"
        )
        return WAITING_FOR_SITE_ID

    raw_text = update.message.text
    site_id = normalize_site_id(raw_text)
    if not site_id:
        await update.message.reply_text(
            "❌ ما قدرتش نقرأ الـID.\n"
            "صيفطو بهذا الشكل:\n"
            "ID:38938378"
        )
        return WAITING_FOR_SITE_ID

    campaign_id = context.user_data.get("campaign_id")
    db_user_id = context.user_data.get("db_user_id")
    promo_code = context.user_data.get("promo_code")
    screenshot_file_id = context.user_data.get("screenshot_file_id")

    if not campaign_id or not db_user_id or not screenshot_file_id:
        user = update.effective_user
        if user:
            db_user_id = create_or_update_user(user.id, user.username, user.first_name)
        active_campaign = get_active_campaign()
        if not active_campaign or not screenshot_file_id:
            await update.message.reply_text(
                "حدث خطأ أو انتهت الجلسة. أرسل /start للبدء من جديد."
            )
            return ConversationHandler.END
        campaign_id = active_campaign["id"]
        promo_code = active_campaign["promo_code"]

    # Verify campaign is still active and can accept requests
    if not can_accept_request(campaign_id):
        await update.message.reply_text(
            "حالياً ما كاين حتى عرض مفتوح.\n"
            "تابع القناة باش تعرف ملي يفتح عرض جديد."
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Insert request
    try:
        req_id = create_request(
            campaign_id=campaign_id,
            user_id=db_user_id,
            site_id=site_id,
            screenshot_file_id=screenshot_file_id,
            status="pending"
        )
    except ValueError as e:
        err_msg = str(e)
        if "benefited" in err_msg.lower():
            await update.message.reply_text(
                "❌ سبق ليك استفدتي من هاد Promo Code.\n"
                "كل شخص يقدر يستافد من هاد الكود مرة وحدة."
            )
        elif "pending" in err_msg.lower():
            await update.message.reply_text(
                "⏳ عندك طلب قيد المراجعة فهاد العرض.\n"
                "غادي يتم التواصل معاك قريباً."
            )
        else:
            await update.message.reply_text(
                "حالياً ما كاين حتى عرض مفتوح.\n"
                "تابع القناة باش تعرف ملي يفتح عرض جديد."
            )
        context.user_data.clear()
        return ConversationHandler.END

    logger.info(
        f"New request created - Request ID: {req_id}, Campaign ID: {campaign_id}, "
        f"DB User ID: {db_user_id}, Site ID: {site_id}"
    )

    # 1. Notify Admin with review buttons if ADMIN_TELEGRAM_ID is configured
    if ADMIN_TELEGRAM_ID:
        try:
            cust_name = update.effective_user.first_name or "مستخدم"
            cust_username_str = f"@{update.effective_user.username}" if update.effective_user.username else "لا يوجد"
            cust_tg_id = update.effective_user.id

            admin_notification = (
                f"📥 طلب مكافأة جديد #{req_id}\n\n"
                f"🎟️ Promo Code: {promo_code}\n"
                f"🆔 Site ID: {site_id}\n\n"
                f"👤 الاسم: {cust_name}\n"
                f"🔗 المعرف: {cust_username_str}\n"
                f"🆔 Telegram ID: {cust_tg_id}\n\n"
                f"⏳ الحالة: قيد المراجعة"
            )

            admin_keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ قبول الطلب", callback_data=f"admin_accept_{req_id}"),
                    InlineKeyboardButton("❌ رفض الطلب", callback_data=f"admin_reject_{req_id}"),
                ]
            ])

            if screenshot_file_id:
                try:
                    await context.bot.send_photo(
                        chat_id=ADMIN_TELEGRAM_ID,
                        photo=screenshot_file_id,
                        caption=admin_notification,
                        reply_markup=admin_keyboard,
                    )
                except Exception as e:
                    logger.warning(f"Could not send photo to admin: {e}")
                    await context.bot.send_message(
                        chat_id=ADMIN_TELEGRAM_ID,
                        text=admin_notification,
                        reply_markup=admin_keyboard,
                    )
            else:
                await context.bot.send_message(
                    chat_id=ADMIN_TELEGRAM_ID,
                    text=admin_notification,
                    reply_markup=admin_keyboard,
                )
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")

    # 2. Customer Confirmation
    confirmation_text = (
        "✅ تسجل الطلب ديالك بنجاح.\n\n"
        f"🎟️ Promo Code: {promo_code}\n"
        f"🆔 Site ID: {site_id}\n\n"
        "⏳ الحالة: قيد المراجعة\n\n"
        "إلى تم قبول الطلب، غادي يتم التواصل معاك."
    )
    await update.message.reply_text(confirmation_text)
    context.user_data.clear()
    return ConversationHandler.END


async def handle_admin_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin acceptance or rejection of a pending request."""
    query = update.callback_query
    if not query:
        return

    admin_user = update.effective_user
    if not admin_user or not ADMIN_TELEGRAM_ID or admin_user.id != ADMIN_TELEGRAM_ID:
        await query.answer("❌ غير مصرح لك بالقيام بهذا الإجراء.", show_alert=True)
        return

    match = re.match(r"^admin_(accept|reject)_(\d+)$", query.data or "")
    if not match:
        await query.answer("بيانات غير صالحة.", show_alert=True)
        return

    action, req_id_str = match.group(1), match.group(2)
    req_id = int(req_id_str)

    target_status = "accepted" if action == "accept" else "rejected"

    # Execute review atomically in database
    success, reason = review_request(req_id, target_status)
    if not success:
        await query.answer(f"⚠️ {reason}", show_alert=True)
        # Update message to remove obsolete action buttons
        req_data = get_request_by_id(req_id)
        if req_data:
            current_status = req_data["status"]
            status_text = "✅ مقبول" if current_status in ("accepted", "approved") else ("❌ مرفوض" if current_status == "rejected" else current_status)
            try:
                if query.message and query.message.photo:
                    new_caption = f"{query.message.caption or ''}\n\n📌 الحالة: {status_text}"
                    await query.edit_message_caption(caption=new_caption, reply_markup=None)
                elif query.message:
                    new_text = f"{query.message.text or ''}\n\n📌 الحالة: {status_text}"
                    await query.edit_message_text(text=new_text, reply_markup=None)
            except Exception:
                pass
        return

    req_data = get_request_by_id(req_id)
    if not req_data:
        await query.answer("تمت معالجة الطلب بنجاح.", show_alert=True)
        return

    action_name_ar = "قبول" if action == "accept" else "رفض"
    await query.answer(f"✅ تم {action_name_ar} الطلب #{req_id}")

    # Update admin message in Telegram UI
    status_label = "✅ تم القبول" if action == "accept" else "❌ تم الرفض"
    try:
        if query.message and query.message.photo:
            new_caption = f"{query.message.caption or ''}\n\n📌 النتيجة: {status_label}"
            await query.edit_message_caption(caption=new_caption, reply_markup=None)
        elif query.message:
            new_text = f"{query.message.text or ''}\n\n📌 النتيجة: {status_label}"
            await query.edit_message_text(text=new_text, reply_markup=None)
    except Exception as e:
        logger.warning(f"Could not update admin message: {e}")

    # Notify Customer
    customer_telegram_id = req_data["telegram_user_id"]
    promo_code = req_data["promo_code"]
    site_id = req_data["site_id"]

    if action == "accept":
        customer_msg = (
            "🎉 تم قبول الطلب ديالك بنجاح!\n\n"
            f"🎟️ Promo Code: {promo_code}\n"
            f"🆔 Site ID: {site_id}\n\n"
            "شكراً لمشاركتك معنا! ✅"
        )
    else:
        benefited_codes = get_user_benefited_promo_codes(req_data["user_id"])
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
        await context.bot.send_message(
            chat_id=customer_telegram_id,
            text=customer_msg
        )
    except Exception as e:
        logger.warning(f"Could not notify customer {customer_telegram_id}: {e}")


async def handle_unexpected_site_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle non-text messages while waiting for Site ID."""
    if update.message:
        await update.message.reply_text(
            "❌ ما قدرتش نقرأ الـID.\n"
            "صيفطو بهذا الشكل:\n"
            "ID:38938378"
        )
    return WAITING_FOR_SITE_ID


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel conversation flow."""
    context.user_data.clear()
    if update.message:
        await update.message.reply_text("تم إلغاء العملية. أرسل /start في أي وقت للبدء من جديد.")
    return ConversationHandler.END


def main() -> None:
    # Ensure database and tables are ready
    initialize_database()

    logger.info("Initializing Telegram Bot...")
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FOR_SCREENSHOT: [
                CallbackQueryHandler(handle_start_submission, pattern="^start_submission$"),
                MessageHandler(filters.Regex("^✅ فهمت، نبدأ$"), handle_start_submission),
                MessageHandler(filters.PHOTO | filters.VIDEO, handle_screenshot),
                MessageHandler(filters.ALL & ~filters.COMMAND, handle_unexpected_screenshot),
            ],
            WAITING_FOR_SITE_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_site_id),
                MessageHandler(filters.ALL & ~filters.COMMAND, handle_unexpected_site_id),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("cancel", cancel),
        ],
        allow_reentry=True,
        per_message=False,
    )

    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(handle_admin_review, pattern=r"^admin_(accept|reject)_\d+$"))
    application.add_handler(build_admin_conversation_handler())

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log unexpected errors cleanly without crashing or exposing secrets."""
        logger.error(f"Telegram Bot exception while handling update: {context.error.__class__.__name__} - {context.error}")

    application.add_error_handler(error_handler)

    logger.info("Bot is running and polling for updates...")
    application.run_polling()


if __name__ == "__main__":
    main()
