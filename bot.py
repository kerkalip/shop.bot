import os
import threading
from flask import Flask
import telebot

# --- ១. បង្កើត Web Server តូចមួយសម្រាប់ Render ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# រត់ Web Server លើ Background Thread
t = threading.Thread(target=run_flask)
t.start()

# --- ២. កូដ Telegram Bot របស់បង ---
TOKEN = '8654200136:AAGTEmmg3Rb5Z36aGlGrn1j3-36JwzsU-Gs'
bot = telebot.TeleBot(TOKEN)

# (ដាក់កូដ @bot.message_handler ផ្សេងៗរបស់បងនៅកន្លែងនេះ...)

# --- ៣. រត់ Bot Polling ---
print("Bot is starting...")
bot.infinity_polling()
