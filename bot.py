import telebot

# Token របស់បង
TOKEN = '8654200136:AAGTEmmg3Rb5Z36aGlGrn1j3-36JwzsU-Gs'

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "សួស្តី! Bot របស់ Vieki Store កំពុងដំណើរការហើយ! 🛒")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, f"អ្នកបានផ្ញើ៖ {message.text}")

print("Bot is starting...")
bot.infinity_polling(skip_pending=True)
