import logging
import os
import asyncio
import json
import random
import time
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, 
    ConversationHandler, CallbackQueryHandler, CallbackContext,
    JobQueue
)
from solana.rpc.api import Client
from solders.pubkey import Pubkey
from solders.keypair import Keypair

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Conversation States ---
SELECTING_SERVICE, SELECTING_PACKAGE, AWAITING_PAYMENT, AWAITING_CONTRACT = range(4)

# --- Bot Configuration ---
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN: raise ValueError("TELEGRAM_BOT_TOKEN not found.")

SOLANA_RPC_URL = os.environ.get('SOLANA_RPC_URL')
if not SOLANA_RPC_URL: raise ValueError("SOLANA_RPC_URL not found.")

TREASURY_PRIVATE_KEY_STR = os.environ.get('TREASURY_WALLET_PRIVATE_KEY')
if not TREASURY_PRIVATE_KEY_STR: raise ValueError("TREASURY_WALLET_PRIVATE_KEY not found.")
try:
    private_key_bytes = bytes(eval(TREASURY_PRIVATE_KEY_STR))
    TREASURY_WALLET = Keypair.from_secret_key(private_key_bytes)
except Exception as e:
    raise ValueError(f"Could not decode the private key. Error: {e}")

DEPOSIT_ADDRESS = '5H5xeKUt1wh5SE8hSJbnh9tsdVgZrUrbGffQjD9HTE9E'
DEPOSIT_PUBKEY = Pubkey.from_string(DEPOSIT_ADDRESS)

# --- User Loyalty System ---
LOYALTY_FILE = "user_loyalty.json"
REFERRAL_BONUS = 0.1  # 0.1 SOL for each successful referral
POINTS_PER_SOL = 100  # 100 loyalty points per SOL spent
POINTS_REDEMPTION_RATE = 0.01  # 0.01 SOL per point

def load_user_data():
    try:
        with open(LOYALTY_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_user_data(data):
    with open(LOYALTY_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_user_data(user_id):
    users = load_user_data()
    user_id_str = str(user_id)
    if user_id_str not in users:
        users[user_id_str] = {
            "points": 0,
            "referrals": 0,
            "total_spent": 0,
            "last_service": None,
            "discount_available": False
        }
        save_user_data(users)
    return users[user_id_str]

def update_user_data(user_id, points=0, spent=0, referral=False):
    users = load_user_data()
    user_id_str = str(user_id)
    if user_id_str not in users:
        users[user_id_str] = {
            "points": 0,
            "referrals": 0,
            "total_spent": 0,
            "last_service": None,
            "discount_available": False
        }
    
    users[user_id_str]["points"] += points
    users[user_id_str]["total_spent"] += spent
    if referral:
        users[user_id_str]["referrals"] += 1
    users[user_id_str]["last_service"] = datetime.now().isoformat()
    
    # Grant discount after 3 services
    if users[user_id_str]["referrals"] >= 3 or users[user_id_str]["total_spent"] >= 10:
        users[user_id_str]["discount_available"] = True
    
    save_user_data(users)
    return users[user_id_str]

# --- Service Packages ---
SERVICE_PACKAGES = {
    'holders': {
        'name': '📈 Token Holders Increase',
        'explanation': "Quickly increase token holders by creating wallets that acquire your token. Boosts on-chain data and attracts investors.",
        'packages': {
            'h_1': {'name': '50 Holders', 'price_sol': 0.5, 'price_lamports': 0.5 * 1e9, 'value': 50},
            'h_2': {'name': '400 Holders', 'price_sol': 1.8, 'price_lamports': 1.8 * 1e9, 'value': 400},
            'h_3': {'name': '700 Holders', 'price_sol': 3.0, 'price_lamports': 3.0 * 1e9, 'value': 700},
            'h_4': {'name': '1000 Holders', 'price_sol': 3.8, 'price_lamports': 3.8 * 1e9, 'value': 1000},
        }
    },
    'market_maker': {
        'name': '📊 Solana Market Maker',
        'explanation': "Market maker bot creates consistent trading volume for your token, improving liquidity and price stability.",
        'packages': {
            'mm_1': {'name': 'Basic Volume', 'price_sol': 0.5, 'price_lamports': 0.5 * 1e9},
            'mm_2': {'name': 'Standard Volume', 'price_sol': 1.8, 'price_lamports': 1.8 * 1e9},
            'mm_3': {'name': 'Advanced Volume', 'price_sol': 3.0, 'price_lamports': 3.0 * 1e9},
            'mm_4': {'name': 'Pro Volume', 'price_sol': 3.8, 'price_lamports': 3.8 * 1e9},
        }
    },
    'poster': {
        'name': '📢 Multi-Group Poster',
        'explanation': "Get your message posted across thousands of crypto Telegram groups to reach a massive audience.",
        'packages': {
            'p_1': {'name': '50 Groups', 'price_sol': 0.18, 'price_lamports': 0.18 * 1e9},
            'p_2': {'name': '300 Groups', 'price_sol': 0.5, 'price_lamports': 0.5 * 1e9},
            'p_3': {'name': '10,000 Groups', 'price_sol': 1.79, 'price_lamports': 1.79 * 1e9},
        }
    },
    'trending': {
        'name': '🚀 DEX Trending (Top 10)',
        'explanation': "All-in-one premium package to push your token into Top 10 trending on DexScreener and DEXTools.",
        'packages': {
            't_1': {'name': 'Top 10 Trending', 'price_sol': 3.57, 'price_lamports': 3.57 * 1e9},
        }
    }
}

# --- Enhanced Features ---
LOYALTY_TIPS = [
    "💡 Pro Tip: Earn 0.1 SOL for each friend you refer who makes a purchase!",
    "⭐ Loyalty Perk: Every SOL spent earns you 100 loyalty points (1 point = 0.00001 SOL discount)!",
    "🎁 Special Offer: Complete 3 services to unlock exclusive discounts!",
    "📈 Market Insight: Tokens with consistent volume tend to attract more organic holders.",
    "🔥 Hot Tip: Combine holder growth with market making for best results!"
]

# --- On-Chain & Service Logic ---
async def verify_payment(expected_amount_lamports: int) -> bool:
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

async def execute_service(service_type: str, package: dict, contract: str, user_id: int):
    logger.info("="*50)
    logger.info(f"EXECUTING SERVICE: {service_type.upper()}")
    logger.info(f"  - Package: {package.get('name')}")
    logger.info(f"  - Contract: {contract}")
    logger.info(f"  - Budget (15%): {int(package.get('price_lamports', 0) * 0.15) / 1e9} SOL")
    logger.info("="*50)
    
    # Update loyalty points
    points_earned = int(package['price_sol'] * POINTS_PER_SOL)
    update_user_data(user_id, points=points_earned, spent=package['price_sol'])
    
    return True

# --- Enhanced Bot Handlers ---
async def start(update: Update, context: CallbackContext) -> int:
    """Displays the main menu with enhanced options"""
    user = update.effective_user
    user_data = get_user_data(user.id)
    
    # Check if coming from referral
    if context.args and context.args[0].startswith('ref_'):
        referrer_id = context.args[0][4:]
        if referrer_id and referrer_id != str(user.id):
            update_user_data(int(referrer_id), referral=True)
            update_user_data(user.id, points=int(REFERRAL_BONUS * POINTS_PER_SOL))
    
    # Welcome message with loyalty status
    points = user_data['points']
    referrals = user_data['referrals']
    welcome_msg = (
        f"👋 Welcome back, {user.first_name}!\n"
        f"⭐ Your Loyalty: {points} points | 👥 Referrals: {referrals}\n\n"
        "Choose a service to boost your token:"
    )
    
    keyboard = [
        [InlineKeyboardButton(SERVICE_PACKAGES['holders']['name'], callback_data='service_holders')],
        [InlineKeyboardButton(SERVICE_PACKAGES['market_maker']['name'], callback_data='service_market_maker')],
        [InlineKeyboardButton(SERVICE_PACKAGES['poster']['name'], callback_data='service_poster')],
        [InlineKeyboardButton(SERVICE_PACKAGES['trending']['name'], callback_data='service_trending')],
        [InlineKeyboardButton("⭐ My Account", callback_data='my_account'),
         InlineKeyboardButton("👥 Refer Friends", callback_data='refer_friends')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(welcome_msg, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(welcome_msg, reply_markup=reply_markup)
    
    return SELECTING_SERVICE

async def select_service(update: Update, context: CallbackContext) -> int:
    """Handles service selection with loyalty tips"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'my_account':
        return await show_account(update, context)
    elif query.data == 'refer_friends':
        return await show_referral(update, context)
    
    service_key = query.data.split('_')[1]
    context.user_data['service'] = service_key
    service_info = SERVICE_PACKAGES[service_key]

    # Add random loyalty tip
    loyalty_tip = random.choice(LOYALTY_TIPS)
    
    await query.edit_message_text(
        text=f"*{service_info['name']}*\n\n{service_info['explanation']}\n\n"
             f"{loyalty_tip}\n\n"
             "To continue, please reply with your token's contract address:",
        parse_mode='Markdown'
    )
    return AWAITING_CONTRACT

async def received_contract(update: Update, context: CallbackContext) -> int:
    """Stores contract and shows packages with loyalty discounts"""
    context.user_data['contract'] = update.message.text
    service_key = context.user_data['service']
    service_info = SERVICE_PACKAGES[service_key]
    
    # Get user loyalty status
    user_data = get_user_data(update.effective_user.id)
    points = user_data['points']
    discount_available = user_data['discount_available']
    
    keyboard = []
    for pkg_key, pkg_info in service_info['packages'].items():
        base_price = pkg_info['price_sol']
        
        # Apply discounts if available
        discount_msg = ""
        if discount_available:
            discounted_price = base_price * 0.9  # 10% discount
            discount_msg = f" (~~{base_price}~~ {discounted_price:.2f} SOL)"
        elif points > 0:
            points_discount = min(points * POINTS_REDEMPTION_RATE, base_price * 0.5)
            discounted_price = base_price - points_discount
            discount_msg = f" (~~{base_price}~~ {discounted_price:.2f} SOL)"
        else:
            discounted_price = base_price
            discount_msg = f" ({base_price} SOL)"
        
        button_text = f"{pkg_info['name']}{discount_msg}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"pkg_{pkg_key}")])
    
    # Add back button
    keyboard.append([InlineKeyboardButton("🔙 Back to Services", callback_data='back_to_services')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    discount_info = ""
    if discount_available:
        discount_info = "\n\n🎁 You qualify for a 10% VIP discount on all packages!"
    elif points > 0:
        discount_info = f"\n\n💎 You have {points} loyalty points ({points * POINTS_REDEMPTION_RATE:.2f} SOL credit) to apply!"
    
    await update.message.reply_text(
        f"Perfect! Now choose a package for *{service_info['name']}*:{discount_info}",
        reply_markup=reply_markup, 
        parse_mode='Markdown'
    )
    return SELECTING_PACKAGE

async def select_package(update: Update, context: CallbackContext) -> int:
    """Handles package selection with loyalty discounts"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'back_to_services':
        return await start(update, context)
    
    pkg_key = query.data.split('_')[1]
    service_key = context.user_data['service']
    package_info = SERVICE_PACKAGES[service_key]['packages'][pkg_key]
    context.user_data['package'] = package_info
    context.user_data['package_key'] = pkg_key
    
    # Calculate final price with discounts
    user_data = get_user_data(query.from_user.id)
    base_price = package_info['price_sol']
    final_price = base_price
    points_used = 0
    
    if user_data['discount_available']:
        final_price = base_price * 0.9
    elif user_data['points'] > 0:
        max_discount = min(user_data['points'] * POINTS_REDEMPTION_RATE, base_price * 0.5)
        final_price = base_price - max_discount
        points_used = int(max_discount / POINTS_REDEMPTION_RATE)
    
    context.user_data['final_price'] = final_price
    context.user_data['points_used'] = points_used
    
    deposit_message = (
        f"You selected: **{package_info['name']}**\n"
        f"Final Price: **{final_price:.4f} SOL**\n\n"
        "Please deposit to:\n"
        f"`{DEPOSIT_ADDRESS}`\n\n"
        "After payment, click below:"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ I Have Paid", callback_data="confirm_payment")],
        [InlineKeyboardButton("🔙 Choose Different Package", callback_data='back_to_packages')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=deposit_message, 
        reply_markup=reply_markup, 
        parse_mode='Markdown'
    )
    return AWAITING_PAYMENT

async def process_payment(update: Update, context: CallbackContext) -> int:
    """Handles payment verification with progress updates"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'back_to_packages':
        return await received_contract(update, context)
    
    user_id = query.from_user.id
    package = context.user_data.get('package')
    final_price = context.user_data.get('final_price', package['price_sol'])
    points_used = context.user_data.get('points_used', 0)
    
    # Send initial processing message
    processing_msg = await query.edit_message_text(
        text="⏳ Verifying your payment on Solana blockchain...\n"
             "[░░░░░░░░░░] 0%",
        parse_mode='Markdown'
    )
    
    # Simulate progress bar
    for i in range(1, 11):
        await asyncio.sleep(2)
        progress = "█" * i + "░" * (10 - i)
        try:
            await context.bot.edit_message_text(
                chat_id=query.message.chat_id,
                message_id=processing_msg.message_id,
                text=f"⏳ Verifying your payment on Solana blockchain...\n"
                     f"[{progress}] {i*10}%",
                parse_mode='Markdown'
            )
        except:
            pass
    
    # Actual verification
    payment_found = False
    expected_amount = int(final_price * 1e9)
    for _ in range(3):
        if await verify_payment(expected_amount):
            payment_found = True
            break
        await asyncio.sleep(10)
    
    if payment_found:
        # Update loyalty points
        points_earned = int(final_price * POINTS_PER_SOL)
        if points_used > 0:
            update_user_data(user_id, points=-points_used)
        update_user_data(user_id, points=points_earned, spent=final_price)
        
        # Execute service
        service_type = context.user_data.get('service')
        contract = context.user_data.get('contract')
        await execute_service(service_type, package, contract, user_id)
        
        # Generate referral link
        ref_link = f"https://t.me/{context.bot.username}?start=ref_{user_id}"
        
        success_msg = (
            "🎉 Payment verified!\n\n"
            f"✅ {package['name']} activated for your token!\n"
            f"⭐ You earned {points_earned} loyalty points!\n\n"
            "Share with friends and earn rewards:\n"
            f"🔗 Your referral link: {ref_link}\n\n"
            "You can /start to request another service"
        )
        
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=success_msg
        )
        
        # Schedule follow-up message
        context.job_queue.run_once(
            send_follow_up, 
            24 * 3600,  # 24 hours later
            chat_id=user_id,
            name=str(user_id)
        )
    else:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ Payment verification failed.\n\n"
                 "Please ensure:\n"
                 "1. You sent exactly the requested amount\n"
                 "2. Transaction is confirmed on Solana\n"
                 "3. You used the correct deposit address\n\n"
                 "Try again or contact support."
        )
    
    return ConversationHandler.END

async def send_follow_up(context: CallbackContext):
    """Sends a follow-up message after service completion"""
    job = context.job
    user_id = job.chat_id
    
    # 30% chance to send special offer
    if random.random() < 0.3:
        services = list(SERVICE_PACKAGES.keys())
        random_service = random.choice(services)
        service_name = SERVICE_PACKAGES[random_service]['name']
        
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🔥 Special Offer! 🔥\n\n"
                 f"Get 15% OFF our {service_name} service today only!\n"
                 "Reply with /start to claim your discount!"
        )
    else:
        # Regular follow-up
        await context.bot.send_message(
            chat_id=user_id,
            text="👋 How's your token performing after our service?\n\n"
                 "We'd love to hear your feedback!\n"
                 "Reply with /start to request another boost"
        )

async def show_account(update: Update, context: CallbackContext) -> int:
    """Displays user's account information"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    user_data = get_user_data(user.id)
    
    # Generate referral link
    ref_link = f"https://t.me/{context.bot.username}?start=ref_{user.id}"
    
    # Format last service date
    last_service = "Never"
    if user_data['last_service']:
        last_date = datetime.fromisoformat(user_data['last_service'])
        last_service = last_date.strftime("%Y-%m-%d %H:%M")
    
    account_msg = (
        f"👤 *Your Account*\n\n"
        f"🆔 ID: `{user.id}`\n"
        f"⭐ Loyalty Points: {user_data['points']} "
        f"(≈ {user_data['points'] * POINTS_REDEMPTION_RATE:.4f} SOL)\n"
        f"👥 Successful Referrals: {user_data['referrals']}\n"
        f"💸 Total Spent: {user_data['total_spent']:.4f} SOL\n"
        f"🕒 Last Service: {last_service}\n\n"
        f"🔗 Your referral link:\n{ref_link}\n\n"
        f"Earn {REFERRAL_BONUS} SOL for each friend who makes a purchase!"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Back to Main", callback_data='back_to_main')],
        [InlineKeyboardButton("👥 Share Referral", 
         url=f"https://t.me/share/url?url={ref_link}&text=Join%20CoinBot%20for%20crypto%20growth%20services!")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=account_msg,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return SELECTING_SERVICE

async def show_referral(update: Update, context: CallbackContext) -> int:
    """Shows referral information"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    ref_link = f"https://t.me/{context.bot.username}?start=ref_{user.id}"
    
    referral_msg = (
        "👥 *Refer Friends & Earn*\n\n"
        "Share your referral link below and earn rewards:\n\n"
        f"• {REFERRAL_BONUS} SOL for each friend's first purchase\n"
        f"• 100 bonus loyalty points per referral\n\n"
        "🔗 Your personal referral link:\n"
        f"`{ref_link}`\n\n"
        "Share directly using the button below:"
    )
    
    keyboard = [
        [InlineKeyboardButton("📤 Share Referral Link", 
         url=f"https://t.me/share/url?url={ref_link}&text=Join%20CoinBot%20for%20crypto%20growth%20services!")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data='back_to_main')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=referral_msg,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return SELECTING_SERVICE

async def cancel(update: Update, context: CallbackContext) -> int:
    """Cancels the current operation"""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Action canceled. You can /start again anytime.")
    else:
        await update.message.reply_text("Action canceled. You can /start again anytime.")
    return ConversationHandler.END

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add job queue for scheduled messages
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(
            send_engagement_message, 
            interval=timedelta(hours=6),
            first=10
        )
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SELECTING_SERVICE: [CallbackQueryHandler(select_service, pattern=r'^(service_|my_account|refer_friends)')],
            AWAITING_CONTRACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_contract)],
            SELECTING_PACKAGE: [CallbackQueryHandler(select_package, pattern=r'^(pkg_|back_)')],
            AWAITING_PAYMENT: [CallbackQueryHandler(process_payment, pattern=r'^(confirm_payment|back_)')],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('account', show_account))
    application.add_handler(CommandHandler('refer', show_referral))
    
    print("Bot is running with enhanced features...")
    application.run_polling()

async def send_engagement_message(context: CallbackContext):
    """Sends engagement messages to active users"""
    job = context.job
    try:
        users = load_user_data()
        now = datetime.now()
        
        for user_id_str, user_data in users.items():
            try:
                user_id = int(user_id_str)
                last_service = datetime.fromisoformat(user_data['last_service']) if user_data['last_service'] else None
                
                # Only message users who have used service in last 30 days
                if last_service and (now - last_service).days <= 30:
                    # 20% chance to send a message to avoid spamming
                    if random.random() < 0.2:
                        tips = [
                            "📈 Pro Tip: Consistent volume attracts more organic traders!",
                            "🔥 Limited Offer: Get 10% bonus holders with your next order!",
                            "💎 New: Try our trending package for maximum visibility!",
                            "👥 Remember: You earn SOL for every friend who joins!",
                            "⭐ Your loyalty points can be redeemed for discounts!"
                        ]
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=random.choice(tips) + "\n\nReply with /start to boost your token!"
                        )
            except Exception as e:
                logger.error(f"Error sending engagement to {user_id_str}: {e}")
    except Exception as e:
        logger.error(f"Engagement message error: {e}")

if __name__ == '__main__':
    # Initialize user data file
    if not os.path.exists(LOYALTY_FILE):
        with open(LOYALTY_FILE, 'w') as f:
            json.dump({}, f)
    
    main()
