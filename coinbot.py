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

# --- Enhanced Service & Package Structure ---
SERVICE_PACKAGES = {
    'holders': {
        'name': '📈 Token Holders Increase',
        'emoji': '📈',
        'color': '#4CAF50',  # Green
        'explanation': "This service quickly increases the number of token holders for your project by creating new wallets that acquire a small amount of your token. This helps your project's on-chain data look more active and attractive to new investors.",
        'packages': {
            'h_1': {'name': '50 Holders', 'price_sol': 0.5, 'price_lamports': 0.5 * 1e9, 'value': 50, 'emoji': '🔹'},
            'h_2': {'name': '400 Holders', 'price_sol': 1.8, 'price_lamports': 1.8 * 1e9, 'value': 400, 'emoji': '🔸'},
            'h_3': {'name': '700 Holders', 'price_sol': 3.0, 'price_lamports': 3.0 * 1e9, 'value': 700, 'emoji': '🔷'},
            'h_4': {'name': '1000 Holders', 'price_sol': 3.8, 'price_lamports': 3.8 * 1e9, 'value': 1000, 'emoji': '💎'},
        }
    },
    'market_maker': {
        'name': '📊 Solana Market Maker',
        'emoji': '📊',
        'color': '#2196F3',  # Blue
        'explanation': "Our Market Maker bot engages in automated trading for your token. It executes batch swaps on major DEXs, creating consistent trading volume. This makes your token appear more liquid and can help stabilize its price.",
        'packages': {
            'mm_1': {'name': 'Basic Volume', 'price_sol': 0.5, 'price_lamports': 0.5 * 1e9, 'emoji': '🔹'},
            'mm_2': {'name': 'Standard Volume', 'price_sol': 1.8, 'price_lamports': 1.8 * 1e9, 'emoji': '🔸'},
            'mm_3': {'name': 'Advanced Volume', 'price_sol': 3.0, 'price_lamports': 3.0 * 1e9, 'emoji': '🔷'},
            'mm_4': {'name': 'Pro Volume', 'price_sol': 3.8, 'price_lamports': 3.8 * 1e9, 'emoji': '💎'},
        }
    },
    'poster': {
        'name': '📢 Multi-Group Poster',
        'emoji': '📢',
        'color': '#FF9800',  # Orange
        'explanation': "Gain massive visibility for your project by having your message automatically posted across thousands of relevant crypto Telegram groups. A perfect way to reach a huge audience of potential investors quickly.",
        'packages': {
            'p_1': {'name': '50 Groups', 'price_sol': 0.18, 'price_lamports': 0.18 * 1e9, 'emoji': '🔹'},
            'p_2': {'name': '300 Groups', 'price_sol': 0.5, 'price_lamports': 0.5 * 1e9, 'emoji': '🔸'},
            'p_3': {'name': '10,000 Groups', 'price_sol': 1.79, 'price_lamports': 1.79 * 1e9, 'emoji': '💎'},
        }
    },
    'trending': {
        'name': '🚀 DEX Trending (Top 10)',
        'emoji': '🚀',
        'color': '#E91E63',  # Pink
        'explanation': "This is our all-in-one premium package. We activate all our powerful features, including market making, holder increases, and high-frequency trading to push your token into the Top 10 trending list on platforms like DexScreener and DEXTools.",
        'packages': {
            't_1': {'name': 'Top 10 Trending', 'price_sol': 3.57, 'price_lamports': 3.57 * 1e9, 'emoji': '💎'},
        }
    }
}

# --- On-Chain & Service Logic (Placeholders) ---

async def verify_payment(expected_amount_lamports: int) -> bool:
    # Implementation remains the same
    pass

async def execute_service(service_type: str, package: dict, contract: str):
    # Implementation remains the same
    pass

# --- UI Improvements ---

def generate_service_menu():
    """Generate visually appealing service menu"""
    keyboard = []
    for service_key, service_info in SERVICE_PACKAGES.items():
        button = InlineKeyboardButton(
            text=f"{service_info['emoji']} {service_info['name']}",
            callback_data=f'service_{service_key}'
        )
        keyboard.append([button])
    return InlineKeyboardMarkup(keyboard)

def generate_package_menu(service_key):
    """Generate visually appealing package menu"""
    service_info = SERVICE_PACKAGES[service_key]
    keyboard = []
    
    # Package cards with emojis and prices
    for pkg_key, pkg_info in service_info['packages'].items():
        button_text = f"{pkg_info['emoji']} {pkg_info['name']} - {pkg_info['price_sol']} SOL"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"pkg_{pkg_key}")])
    
    # Back button
    keyboard.append([InlineKeyboardButton("🔙 Back to Services", callback_data="back_to_services")])
    
    return InlineKeyboardMarkup(keyboard)

def format_service_card(service_info):
    """Format service information as a visual card"""
    return (
        f"✨ *{service_info['name']}* ✨\n\n"
        f"{service_info['explanation']}\n\n"
        "👇 *Please reply with your token's contract address below:*"
    )

def format_package_card(package_info):
    """Format package information as a visual card"""
    return (
        f"📦 *Selected Package*: {package_info['emoji']} {package_info['name']}\n\n"
        f"💳 *Price*: `{package_info['price_sol']} SOL`\n\n"
        "👇 *Send payment to the address below:*"
    )

def format_payment_card(package_info):
    """Format payment information as a visual card"""
    return (
        f"💸 *Payment Required*: `{package_info['price_sol']} SOL`\n\n"
        f"🏦 *Deposit Address*:\n`{DEPOSIT_ADDRESS}`\n\n"
        "🔍 *After payment, click the button below to verify*\n"
        "⏱️ *Note: Transactions usually take <30 seconds to detect*"
    )

# --- Main Bot Conversation Handlers ---

async def start(update: Update, context: CallbackContext) -> int:
    """Displays the main menu of services with enhanced UI"""
    welcome_msg = (
        "🌟 *Welcome to CoinBoost Bot!* 🌟\n\n"
        "Accelerate your token's growth with our premium services:\n"
        "▫️ Increase holders\n▫️ Boost trading volume\n"
        "▫️ Telegram promotions\n▫️ Trending campaigns\n\n"
        "👇 *Select a service to begin:*"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            welcome_msg,
            reply_markup=generate_service_menu(),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            welcome_msg,
            reply_markup=generate_service_menu(),
            parse_mode='Markdown'
        )
    return SELECTING_SERVICE

async def select_service(update: Update, context: CallbackContext) -> int:
    """Handles service selection with enhanced UI"""
    query = update.callback_query
    await query.answer()
    
    service_key = query.data.split('_')[1]
    context.user_data['service'] = service_key
    service_info = SERVICE_PACKAGES[service_key]

    await query.edit_message_text(
        text=format_service_card(service_info),
        reply_markup=None,
        parse_mode='Markdown'
    )
    return AWAITING_CONTRACT

async def received_contract(update: Update, context: CallbackContext) -> int:
    """Shows package selection with enhanced UI"""
    context.user_data['contract'] = update.message.text
    service_key = context.user_data['service']
    service_info = SERVICE_PACKAGES[service_key]
    
    await update.message.reply_text(
        f"✅ *Contract Received!* ✅\n\n"
        f"Token Contract: `{update.message.text[:12]}...`\n\n"
        f"👇 *Select a package for {service_info['name']}:*",
        reply_markup=generate_package_menu(service_key),
        parse_mode='Markdown'
    )
    return SELECTING_PACKAGE

async def select_package(update: Update, context: CallbackContext) -> int:
    """Handles package selection with enhanced UI"""
    query = update.callback_query
    await query.answer()

    pkg_key = query.data.split('_', 1)[1]
    service_key = context.user_data['service']
    package_info = SERVICE_PACKAGES[service_key]['packages'][pkg_key]
    context.user_data['package'] = package_info

    # Create payment card
    payment_msg = (
        f"{format_package_card(package_info)}\n\n"
        f"{format_payment_card(package_info)}"
    )
    
    keyboard = [[InlineKeyboardButton("✅ Verify Payment", callback_data="confirm_payment")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=payment_msg,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return AWAITING_PAYMENT

async def process_payment(update: Update, context: CallbackContext) -> int:
    """Payment processing with enhanced UI"""
    query = update.callback_query
    await query.answer()
    
    # Show processing animation
    processing_msg = (
        "🔍 *Verifying Payment...*\n\n"
        "⏳ Checking blockchain transactions\n"
        "⏱️ Usually takes 15-30 seconds\n"
        "🔄 Please wait..."
    )
    await query.edit_message_text(
        text=processing_msg,
        parse_mode='Markdown'
    )
    
    package = context.user_data.get('package')
    if not package:
        await query.message.reply_text("❌ Session expired. Please /start again.")
        return ConversationHandler.END

    expected_amount = package['price_lamports']
    payment_found = False
    for i in range(1, 7):  # 6 checks, 10 seconds apart
        if await verify_payment(int(expected_amount)):
            payment_found = True
            break
            
        # Update progress
        progress = "🟢" * i + "⚪️" * (6 - i)
        await query.edit_message_text(
            text=f"{processing_msg}\n\nProgress: {progress}",
            parse_mode='Markdown'
        )
        await asyncio.sleep(10)

    if payment_found:
        success_msg = (
            "🎉 *Payment Verified!* 🎉\n\n"
            "✅ Transaction confirmed on Solana\n"
            "🚀 Starting your service now..."
        )
        await query.edit_message_text(
            text=success_msg,
            parse_mode='Markdown'
        )
        
        service_type = context.user_data.get('service')
        contract = context.user_data.get('contract')
        success = await execute_service(service_type, package, contract)
        
        if success:
            completion_msg = (
                "✨ *Service Completed!* ✨\n\n"
                "✅ All tasks finished successfully!\n"
                "📊 Your token metrics are being boosted\n\n"
                "Thank you for using CoinBoost! 🚀\n"
                "You can /start again anytime."
            )
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=completion_msg,
                parse_mode='Markdown'
            )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="⚠️ Service encountered an issue. Our team has been notified and will contact you shortly.",
                parse_mode='Markdown'
            )
    else:
        error_msg = (
            "❌ *Payment Not Found* ❌\n\n"
            "We couldn't verify your transaction after 1 minute.\n\n"
            "Possible reasons:\n"
            "▫️ Insufficient SOL amount sent\n"
            "▫️ Transaction not confirmed yet\n"
            "▫️ Wrong deposit address used\n\n"
            "Please double-check and try again, or /start over."
        )
        await query.edit_message_text(
            text=error_msg,
            parse_mode='Markdown'
        )
    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext) -> int:
    """Enhanced cancellation message"""
    cancel_msg = (
        "❌ *Action Cancelled* ❌\n\n"
        "You can /start again anytime to boost your token!"
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            cancel_msg,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            cancel_msg,
            parse_mode='Markdown'
        )
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
                CallbackQueryHandler(start, pattern=r'^back_to_services$')
            ],
            AWAITING_PAYMENT: [CallbackQueryHandler(process_payment, pattern=r'^confirm_payment$')],
        },
        fallbacks=[CommandHandler('cancel', cancel), CallbackQueryHandler(cancel)],
    )
    application.add_handler(conv_handler)
    print("🚀 CoinBoost Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
