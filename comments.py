# async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Start tracking the token against SOL with a unique alert ID, max 10 tokens per user."""
#     chat_id = update.effective_chat.id
#     user_alerts = [alert_id for alert_id, data in user_tracking.items() if data["chat_id"] == chat_id]
#     if len(user_alerts) >= 10:
#         await update.message.reply_text("⚠️ You can only track a maximum of 10 tokens at a time. Delete some before adding new ones.")
#         return

#     try:
#         token_address = context.args[0]
#         pair_address, token_name = get_pair_address(token_address)

#         if pair_address:
#             token_price, market_cap = fetch_token_price(pair_address)
#             if token_price:
#                 alert_id = str(uuid.uuid4())[:8]  
#                 user_tracking[alert_id] = {
#                     "chat_id": chat_id,
#                     "token_name": token_name,
#                     "token_address": token_address,
#                     "pair_address": pair_address,
#                     "base_price": token_price,
#                     "market_cap": market_cap,
#                     "last_multiple": 1,
#                 }
#                 save_tracking_data()  # Save to Firebase
#                 await update.message.reply_text(
#                     f"🔔 Tracking Started!\n"
#                     f"📌 Alert ID: `{alert_id}`\n"
#                     f"🪙 Token: {token_name} ({token_address})\n"
#                     f"💰 Starting Price: ${token_price:.4f}\n"
#                     f"🏦 Market Cap: ${market_cap:,.2f}\n"
#                     f"❌ Use `/delete {alert_id}` to stop tracking.", parse_mode="Markdown"
#                 )
#             else:
#                 await update.message.reply_text("❌ Failed to fetch the token price.")
#         else:
#             await update.message.reply_text("❌ Could not find a SOL trading pair for this token.")
#     except IndexError:
#         await update.message.reply_text("⚠️ Please provide a token address. Example:\n`/track 5D27E...pump`")

##