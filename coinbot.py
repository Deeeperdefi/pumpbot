import logging
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler, CallbackContext

# Import Solana libraries
from solana.rpc.api import Client
from solders.pubkey import Pubkey
from solders.keypair import Keypair

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- NEW Conversation States ---
SELECTING_SERVICE, SELECTING_PACKAGE, AWAITING_PAYMENT, AWAITING_CONTRACT = range(4)

# --- Bot Configuration ---
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN: raise ValueError("TELEGRAM_BOT_TOKEN not found.")

SOLANA_RPC_URL = os.environ.get('SOLANA_RPC_URL')
if not SOLANA_RPC_URL: raise ValueError("SOLANA_RPC_URL not found.")

TREASURY_PRIVATE_KEY_STR = os.environ.get('TREASURY_WALLET_PRIVATE_KEY')
if not TREASURY_PRIVATE_KEY_STR: raise ValueError("TREASURY_WALLET_PRIVATE_KEY not found.")
try:
    # Use from_base58_string to correctly decode the private key.
    TREASURY_WALLET = Keypair.from_base58_string(TREASURY_PRIVATE_KEY_STR)
except Exception as e:
    raise ValueError(f"Could not decode the private key from Base58. Ensure it's a valid Base58 string. Error: {e}")

DEPOSIT_ADDRESS = '5H5xeKUt1wh5SE8hSJbnh9tsdVgZrUrbGffQjD9HTE9E'
DEPOSIT_PUBKEY = Pubkey.from_string(DEPOSIT_ADDRESS)

# --- NEW Service & Package Structure ---
# Prices for poster/trending converted from USD to SOL (assuming SOL ~$140)
SERVICE_PACKAGES = {
    'holders': {
        'name': '📈 Token Holders Increase',
        'explanation': "This service quickly increases the number of token holders for your project by creating new wallets that acquire a small amount of your token. This helps your project's on-chain data look more active and attractive to new investors.",
        'packages': {
            'h_1': {'name': '50 Holders', 'price_sol': 0.5, 'price_lamports': 0.5 * 1e9, 'value': 50},
            'h_2': {'name': '400 Holders', 'price_sol': 1.8, 'price_lamports': 1.8 * 1e9, 'value': 400},
            'h_3': {'name': '700 Holders', 'price_sol': 3.0, 'price_lamports': 3.0 * 1e9, 'value': 700},
            'h_4': {'name': '1000 Holders', 'price_sol': 3.8, 'price_lamports': 3.8 * 1e9, 'value': 1000},
        }
    },
    'market_maker': {
        'name': '📊 Solana Market Maker',
        'explanation': "Our Market Maker bot engages in automated trading for your token. It executes batch swaps on major DEXs, creating consistent trading volume. This makes your token appear more liquid and can help stabilize its price.",
        'packages': {
            'mm_1': {'name': 'Basic Volume', 'price_sol': 0.5, 'price_lamports': 0.5 * 1e9},
            'mm_2': {'name': 'Standard Volume', 'price_sol': 1.8, 'price_lamports': 1.8 * 1e9},
            'mm_3': {'name': 'Advanced Volume', 'price_sol': 3.0, 'price_lamports': 3.0 * 1e9},
            'mm_4': {'name': 'Pro Volume', 'price_sol': 3.8, 'price_lamports': 3.8 * 1e9},
        }
    },
    'poster': {
        'name': '📢 Multi-Group Poster',
        'explanation': "Gain massive visibility for your project by having your message automatically posted across thousands of relevant crypto Telegram groups. A perfect way to reach a huge audience of potential investors quickly.",
        'packages': {
            'p_1': {'name': '50 Groups', 'price_sol': 0.18, 'price_lamports': 0.18 * 1e9}, # ~$25
            'p_2': {'name': '300 Groups', 'price_sol': 0.5, 'price_lamports': 0.5 * 1e9},   # ~$70
            'p_3': {'name': '10,000 Groups', 'price_sol': 1.79, 'price_lamports': 1.79 * 1e9},# ~$250
        }
    },
    'trending': {
        'name': '🚀 DEX Trending (Top 10)',
        'explanation': "This is our all-in-one premium package. We activate all our powerful features, including market making, holder increases, and high-frequency trading to push your token into the Top 10 trending list on platforms like DexScreener and DEXTools.",
        'packages': {
            't_1': {'name': 'Top 10 Trending', 'price_sol': 3.57, 'price_lamports': 3.57 * 1e9}, # ~$500
        }
    }
}

# --- On-Chain & Service Logic (Placeholders) ---

async def verify_payment(expected_amount_lamports: int) -> bool:
    # This function remains the same, it's already robust.
    try:
        solana_client = Client(SOLANA_RPC_URL)
        signatures = solana_client.get_signatures_for_address(DEPOSIT_PUBKEY, limit=20).value
        if not signatures: return False
        for sig_info in signatures:
            tx_details = solana_client.get_transaction(sig_info.signature, max_supported_transaction_version=0).value
            if tx_details and tx_details.transaction.meta:
                meta = tx_details.transaction.meta
                try:
                    idx = tx_details.transaction.transaction.message.account_keys.index(DEPOSIT_PUBKEY)
                    if abs((meta.post_balances[idx] - meta.pre_balances[idx]) - expected_amount_lamports) < 1000:
                        logger.info(f"Payment verified! Signature: {sig_info.signature}")
                        return True
                except (ValueError, IndexError): continue
    except Exception as e:
        logger.error(f"Payment verification error: {e}")
    return False

async def execute_service(service_type: str, package: dict, contract: str):
    logger.info("="*50)
    logger.info(f"EXECUTING SERVICE: {service_type.upper()}")
    logger.info(f"  - Package: {package.get('name')}")
    logger.info(f"  - Contract: {contract}")
    logger.info(f"  - Budget (15%): {int(package.get('price_lamports', 0) * 0.15) / 1e9} SOL")
    logger.info("="*50)
    # Here you would add the specific logic for each service type
    return True


# --- Main Bot Conversation Handlers ---

async def start(update: Update, context: CallbackContext) -> int:
    """Displays the main menu of services."""
    keyboard = [
        [InlineKeyboardButton(SERVICE_PACKAGES['holders']['name'], callback_data='service_holders')],
        [InlineKeyboardButton(SERVICE_PACKAGES['market_maker']['name'], callback_data='service_market_maker')],
        [InlineKeyboardButton(SERVICE_PACKAGES['poster']['name'], callback_data='service_poster')],
        [InlineKeyboardButton(SERVICE_PACKAGES['trending']['name'], callback_data='service_trending')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Check if this is a new message or an edit from a callback
    if update.callback_query:
        await update.callback_query.edit_message_text("👋 Welcome to CoinBot! Please select a service to begin:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("👋 Welcome to CoinBot! Please select a service to begin:", reply_markup=reply_markup)
    return SELECTING_SERVICE

async def select_service(update: Update, context: CallbackContext) -> int:
    """Handles the user's main service choice, explains it, and asks for the contract."""
    query = update.callback_query
    await query.answer()
    
    service_key = query.data.split('_')[1]
    context.user_data['service'] = service_key
    service_info = SERVICE_PACKAGES[service_key]

    await query.edit_message_text(
        text=f"*{service_info['name']}*\n\n{service_info['explanation']}\n\nTo continue, please reply with your token's contract address.",
        parse_mode='Markdown'
    )
    return AWAITING_CONTRACT

async def received_contract(update: Update, context: CallbackContext) -> int:
    """Stores the contract and shows the relevant packages."""
    context.user_data['contract'] = update.message.text
    service_key = context.user_data['service']
    service_info = SERVICE_PACKAGES[service_key]
    
    keyboard = []
    for pkg_key, pkg_info in service_info['packages'].items():
        button_text = f"{pkg_info['name']} ({pkg_info['price_sol']} SOL)"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"pkg_{pkg_key}")])
    
    # ADDED: A back button for better UX
    keyboard.append([InlineKeyboardButton("⬅️ Back to Services", callback_data="back_to_services")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"Perfect! Now choose a package for *{service_info['name']}*:", reply_markup=reply_markup, parse_mode='Markdown')
    return SELECTING_PACKAGE

async def select_package(update: Update, context: CallbackContext) -> int:
    """Handles package selection and prompts for payment."""
    query = update.callback_query
    await query.answer()

    # FIXED: Correctly parse the package key from the callback data
    pkg_key = query.data.split('_', 1)[1]
    service_key = context.user_data['service']
    package_info = SERVICE_PACKAGES[service_key]['packages'][pkg_key]
    context.user_data['package'] = package_info

    deposit_message = (
        f"You have selected: **{package_info['name']}**.\n\n"
        f"To proceed, please deposit **{package_info['price_sol']} SOL** to the address below. After paying, return here and click 'Confirm Payment'.\n\n"
        f"`{DEPOSIT_ADDRESS}`\n\n"
        "(Tap to copy the address)"
    )
    keyboard = [[InlineKeyboardButton("✅ I Have Paid", callback_data="confirm_payment")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=deposit_message, reply_markup=reply_markup, parse_mode='Markdown')
    return AWAITING_PAYMENT

async def process_payment(update: Update, context: CallbackContext) -> int:
    """Verifies the payment and executes the chosen service."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="⏳ Verifying your payment on the blockchain. This may take up to a minute, please wait...")

    package = context.user_data.get('package')
    if not package:
        await query.message.reply_text("Error: Session expired. Please /start again.")
        return ConversationHandler.END

    expected_amount = package['price_lamports']
    payment_found = False
    for _ in range(6): # 6 checks, 10 seconds apart
        if await verify_payment(int(expected_amount)):
            payment_found = True
            break
        await asyncio.sleep(10)

    if payment_found:
        await query.message.reply_text("🎉 Payment verified and received!")
        service_type = context.user_data.get('service')
        contract = context.user_data.get('contract')
        success = await execute_service(service_type, package, contract)
        
        if success:
            await query.message.reply_text("✅ Congrats, all work is done! Thank you for using CoinBot.\n\nYou can /start a new service anytime.")
        else:
            await query.message.reply_text("There was an issue processing your service. Please contact support.")
    else:
        await query.message.reply_text(
            "❌ We could not find your payment on the blockchain after 1 minute.\n\n"
            "Please ensure you sent the correct amount and try again, or /start over."
        )
    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext) -> int:
    """Cancels the current operation."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Action canceled. You can /start again anytime.")
    else:
        await update.message.reply_text("Action canceled. You can /start again anytime.")
    return ConversationHandler.END

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SELECTING_SERVICE: [CallbackQueryHandler(select_service, pattern=r'^service_.*$')],
            AWAITING_CONTRACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_contract)],
            SELECTING_PACKAGE: [
                CallbackQueryHandler(select_package, pattern=r'^pkg_.*$'),
                # ADDED: Handler for the new back button
                CallbackQueryHandler(start, pattern=r'^back_to_services$')
            ],
            AWAITING_PAYMENT: [CallbackQueryHandler(process_payment, pattern=r'^confirm_payment$')],
        },
        fallbacks=[CommandHandler('cancel', cancel), CallbackQueryHandler(cancel)],
    )
    application.add_handler(conv_handler)
    print("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
