import os
import threading
from flask import Flask
import telebot

# 1. Web Server សម្រាប់ Render
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# រត់ Web Server
t = threading.Thread(target=run_flask)
t.start()

# 2. ដាក់ Token ពិតប្រាកដរបស់បងនៅទីនេះ (ចន្លោះសញ្ញា '' )
TOKEN = '8654200136:AAGTEmmg3Rb5Z36aGlGrn1j3-36JwzsU-Gsះ'
bot = telebot.TeleBot(TOKEN)

# 3. កូដឆ្លើយតប Telegram
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "សួស្តី! Bot កំពុងដំណើរការហើយ! 🛒")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, f"អ្នកបានផ្ញើ៖ {message.text}")

# 4. Start Bot Polling
if __name__ == '__main__':
    print("Bot is starting...")
    bot.infinity_polling(skip_pending=True)
