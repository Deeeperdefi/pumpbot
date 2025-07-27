import logging
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler, CallbackContext

# Import Solana libraries for on-chain verification
from solana.rpc.api import Client
from solders.pubkey import Pubkey

# Enable logging
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
    raise ValueError("No TELEGRAM_BOT_TOKEN found in environment variables.")

# NEW: Add your QuickNode RPC URL as an environment variable
SOLANA_RPC_URL = os.environ.get('SOLANA_RPC_URL')
if not SOLANA_RPC_URL:
    raise ValueError("No SOLANA_RPC_URL found in environment variables.")

DEPOSIT_ADDRESS = '5H5xeKUt1wh5SE8hSJbnh9tsdVgZrUrbGffQjD9HTE9E'
DEPOSIT_PUBKEY = Pubkey.from_string(DEPOSIT_ADDRESS)

# --- Payment Verification Logic ---

# Map payment options to the required SOL amount in Lamports (1 SOL = 1,000,000,000 Lamports)
PAYMENT_AMOUNTS = {
    'option_1': 0.5 * 1e9,
    'option_2': 1.8 * 1e9,
    'option_3': 3.0 * 1e9,
    'option_4': 3.8 * 1e9,
    'option_5': 6.0 * 1e9,
}

async def verify_payment(expected_amount_lamports: int) -> bool:
    """
    Connects to the Solana blockchain to verify if a recent transaction
    of the expected amount was sent to the deposit address.
    """
    try:
        solana_client = Client(SOLANA_RPC_URL)
        # Get the most recent transaction signatures for the deposit address
        signatures = solana_client.get_signatures_for_address(DEPOSIT_PUBKEY, limit=10).value
        
        if not signatures:
            logger.info("No recent transactions found for the address.")
            return False

        for sig_info in signatures:
            # Fetch the full transaction details
            tx_details = solana_client.get_transaction(sig_info.signature, max_supported_transaction_version=0).value
            if tx_details:
                pre_balances = tx_details.transaction.meta.pre_balances
                post_balances = tx_details.transaction.meta.post_balances
                account_keys = tx_details.transaction.transaction.message.account_keys

                # Find the index for our deposit address
                try:
                    deposit_account_index = account_keys.index(DEPOSIT_PUBKEY)
                    
                    # Check if the balance increased by the expected amount
                    balance_before = pre_balances[deposit_account_index]
                    balance_after = post_balances[deposit_account_index]
                    
                    if balance_after - balance_before == expected_amount_lamports:
                        logger.info(f"Payment verified! Signature: {sig_info.signature}")
                        return True
                except ValueError:
                    # This transaction did not involve our deposit address directly
                    continue
                    
    except Exception as e:
        logger.error(f"An error occurred during payment verification: {e}")
        return False
        
    logger.info("No matching payment found in recent transactions.")
    return False

# --- Main Bot Functions ---

async def start(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Welcome to CoinBot, {user.first_name}!\n\n"
        "I can help you get more holders for your Solana token.\n\n"
        "First, please send me your token's contract address."
    )
    return ASK_CONTRACT

async def ask_for_contract(update: Update, context: CallbackContext) -> int:
    context.user_data['contract_address'] = update.message.text
    await update.message.reply_text("Great! Now, please tell me the name of your token.")
    return ASK_TOKEN_NAME

async def ask_for_token_name(update: Update, context: CallbackContext) -> int:
    context.user_data['token_name'] = update.message.text
    await update.message.reply_text(f"Perfect! You've set the token: {context.user_data['token_name']}.")
    return await show_payment_options(update, context)

async def show_payment_options(update: Update, context: CallbackContext) -> int:
    keyboard = [
        [InlineKeyboardButton("📦 50 Holders (0.5 SOL)", callback_data='option_1')],
        [InlineKeyboardButton("🚀 400 Holders (1.8 SOL)", callback_data='option_2')],
        [InlineKeyboardButton("🌟 700 Holders (3.0 SOL)", callback_data='option_3')],
        [InlineKeyboardButton("🔥 1000 Holders (3.8 SOL)", callback_data='option_4')],
        [InlineKeyboardButton("💎 DexScreener/Pump.fun Feature (6.0 SOL)", callback_data='option_5')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "Please choose a package to increase your token holders:"
    if update.callback_query:
        await update.callback_query.message.edit_text(message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)
    return SHOW_OPTIONS

async def handle_payment_choice(update: Update, context: CallbackContext) -> int:
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
        f"To proceed, please deposit the required SOL amount to the address below. After paying, return here and click 'Confirm Payment'.\n\n"
        f"`{DEPOSIT_ADDRESS}`\n\n"
        "(Tap to copy the address)"
    )
    keyboard = [[InlineKeyboardButton("✅ I Have Paid", callback_data='confirm_payment')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=deposit_message, reply_markup=reply_markup, parse_mode='Markdown')
    return AWAIT_SCREENSHOT

async def prompt_for_verification(update: Update, context: CallbackContext) -> int:
    """
    This function is triggered when the user clicks 'I Have Paid'.
    It starts the on-chain verification process.
    """
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="⏳ Verifying your payment on the blockchain, please wait...")

    chosen_option = context.user_data.get('chosen_option')
    expected_amount = PAYMENT_AMOUNTS.get(chosen_option)

    if not expected_amount:
        await query.message.reply_text("Error: Could not determine payment amount. Please /start again.")
        return ConversationHandler.END

    # Check for payment for up to 2 minutes (12 checks, 10 seconds apart)
    payment_found = False
    for i in range(12):
        if await verify_payment(expected_amount):
            payment_found = True
            break
        await asyncio.sleep(10) # Wait before checking again

    if payment_found:
        await query.message.reply_text(
            "🎉 Payment verified and received!\n\n"
            "Your holder increase is now being processed."
        )
    else:
        await query.message.reply_text(
            "❌ We could not find your payment on the blockchain after 2 minutes.\n\n"
            "Please ensure you sent the correct amount and try again later, or contact support. You can /start a new request."
        )
        
    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text('Action canceled. Send /start anytime to begin again.')
    return ConversationHandler.END

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            ASK_CONTRACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_for_contract)],
            ASK_TOKEN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_for_token_name)],
            SHOW_OPTIONS: [CallbackQueryHandler(handle_payment_choice)],
            AWAIT_SCREENSHOT: [CallbackQueryHandler(prompt_for_verification, pattern='^confirm_payment$')],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(conv_handler)
    print("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
