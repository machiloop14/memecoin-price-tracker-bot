import requests
import firebase_admin
from firebase_admin import credentials, firestore
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio
import uuid
import json
import os

# ==============================
# 🔹 Firebase Initialization
# ==============================
firebase_creds_json = os.getenv("FIREBASE_CREDENTIALS")
if not firebase_creds_json:
    raise ValueError("❌ FIREBASE_CREDENTIALS environment variable not set!")

try:
    cred_dict = json.loads(firebase_creds_json)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    raise RuntimeError(f"❌ Failed to initialize Firebase: {e}")

# ==============================
# 🔹 Telegram Bot Token
# ==============================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN environment variable not set!")

bot = Bot(token=TELEGRAM_BOT_TOKEN)

# ==============================
# 🔹 Global tracking dictionary
# ==============================
user_tracking = {}  # Stores alerts by alert_id


def load_tracking_data():
    """Load tracked tokens from Firebase Firestore on startup."""
    global user_tracking
    user_tracking.clear()
    docs = db.collection("tracked_tokens").stream()
    for doc in docs:
        user_tracking[doc.id] = doc.to_dict()


def save_tracking_data():
    """Update only last_multiple values in Firestore."""
    for alert_id, alert_data in user_tracking.items():
        try:
            db.collection("tracked_tokens").document(alert_id).update({
                "last_multiple": alert_data["last_multiple"]
            })
        except Exception as e:
            print(f"⚠️ Error updating alert {alert_id}: {e}")


def delete_tracking_data(alert_id):
    """Delete a specific tracking alert from Firestore."""
    db.collection("tracked_tokens").document(alert_id).delete()


def get_pair_address(token_address):
    """Finds the correct SOL trading pair for the given token address and returns token name."""
    url = f"https://api.dexscreener.com/latest/dex/search?q={token_address}"
    try:
        response = requests.get(url, timeout=10)
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Network error: {e}")
        return None, None

    if response.status_code == 200:
        data = response.json()
        pairs = data.get("pairs", [])
        for pair in pairs:
            if "SOL" in pair["baseToken"]["symbol"] or "SOL" in pair["quoteToken"]["symbol"]:
                token_name = pair["baseToken"]["name"]
                return pair["pairAddress"], token_name
    return None, None


def fetch_token_price(pair_address):
    """Fetch the current price and market cap of the token in the SOL pair."""
    url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_address}"
    try:
        response = requests.get(url, timeout=10)
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Network error: {e}")
        return None, None

    if response.status_code == 200:
        data = response.json()
        if "pairs" in data and data["pairs"]:
            pair_data = data["pairs"][0]
            price = float(pair_data.get("priceUsd", 0))
            market_cap = float(pair_data.get("fdv", 0))
            return price, market_cap
    return None, None


# ==============================
# 🔹 Telegram Commands
# ==============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome! Send `/track <token_address>` and I'll monitor its price against SOL."
    )


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_alerts = [a for a, d in user_tracking.items() if d["chat_id"] == chat_id]
    if len(user_alerts) >= 10:
        await update.message.reply_text("⚠️ Max 10 tokens per user. Delete one to add more.")
        return

    try:
        token_address = context.args[0]
    except IndexError:
        await update.message.reply_text("⚠️ Usage: `/track <token_address>`", parse_mode="Markdown")
        return

    pair_address, token_name = get_pair_address(token_address)
    if not pair_address:
        await update.message.reply_text("❌ Could not find a SOL pair for this token.")
        return

    token_price, market_cap = fetch_token_price(pair_address)
    if not token_price:
        await update.message.reply_text("❌ Failed to fetch token price.")
        return

    alert_id = str(uuid.uuid4())[:8]
    user_tracking[alert_id] = {
        "alert_id": alert_id,
        "chat_id": chat_id,
        "token_name": token_name,
        "token_address": token_address,
        "pair_address": pair_address,
        "base_price": token_price,
        "market_cap": market_cap,
        "last_multiple": 1,
    }
    db.collection("tracked_tokens").document(alert_id).set(user_tracking[alert_id])

    await update.message.reply_text(
        f"🔔 Tracking Started!\n"
        f"📌 Alert ID: `{alert_id}`\n"
        f"🪙 Token: {token_name}\n"
        f"💰 Start Price: ${token_price:.4f}\n"
        f"🏦 Market Cap: ${market_cap:,.2f}\n"
        f"❌ Delete: `/delete {alert_id}`",
        parse_mode="Markdown"
    )


async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        alert_id = context.args[0]
    except IndexError:
        await update.message.reply_text("⚠️ Usage: `/delete <alert_id>`")
        return

    if alert_id in user_tracking:
        del user_tracking[alert_id]
        delete_tracking_data(alert_id)
        await update.message.reply_text(f"✅ Alert `{alert_id}` deleted.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Alert ID not found.")


async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    docs = db.collection("tracked_tokens").where("chat_id", "==", chat_id).stream()
    alerts = [doc.to_dict() for doc in docs]

    if not alerts:
        await update.message.reply_text("📭 No active alerts.")
        return

    message = "📋 **Your Alerts:**\n"
    for i, data in enumerate(alerts, 1):
        current_price, current_cap = fetch_token_price(data["pair_address"])
        multiple = current_price / data["base_price"] if current_price else "N/A"

        message += (
            f"\n{i}. 🪙 {data['token_name']}\n"
            f"   📌 ID: `{data['alert_id']}`\n"
            f"   💰 Base: ${data['base_price']:.4f}\n"
            f"   💰 Current: {current_price if current_price else 'N/A'}\n"
            f"   🏦 Base Cap: ${data['market_cap']:,.2f}\n"
            f"   🏦 Current Cap: {current_cap if current_cap else 'N/A'}\n"
            f"   🔢 Multiple: {multiple}\n"
        )

    await update.message.reply_text(message, parse_mode="Markdown")


# ==============================
# 🔹 Monitoring Loop
# ==============================
async def monitor_prices():
    while True:
        for alert_id, data in list(user_tracking.items()):
            current_price, _ = fetch_token_price(data["pair_address"])
            if current_price:
                multiple = current_price / data["base_price"]
                next_multiple = data["last_multiple"] + 1
                if multiple >= next_multiple:
                    await bot.send_message(
                        data["chat_id"],
                        f"🚀 **{data['token_name']} hit {next_multiple}x!**\n"
                        f"💰 Base: ${data['base_price']:.4f}\n"
                        f"💰 Now: ${current_price:.4f}",
                        parse_mode="Markdown"
                    )
                    user_tracking[alert_id]["last_multiple"] = next_multiple
                    save_tracking_data()
        await asyncio.sleep(60)


# ==============================
# 🔹 Main Entrypoint
# ==============================
def main():
    load_tracking_data()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("track", track))
    app.add_handler(CommandHandler("delete", delete))
    app.add_handler(CommandHandler("list", list_alerts))

    loop = asyncio.get_event_loop()
    loop.create_task(monitor_prices())
    app.run_polling()


if __name__ == "__main__":
    main()
