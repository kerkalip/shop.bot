import telebot
from telebot import types

TOKEN = '8654200136:AAGTEmmg3Rb5Z36aGlGrn1j3-36JwzsU-Gs'
bot = telebot.TeleBot(TOKEN)

# ពេលគេចុច /start ឱ្យចេញ Menu ចុច
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn1 = types.KeyboardButton('👤 គណនីរបស់ខ្ញុំ')
    btn2 = types.KeyboardButton('💳 បញ្ចូលលុយ')
    btn3 = types.KeyboardButton('🛒 ទិញ Account Blox Fruit')
    btn4 = types.KeyboardButton('🆘 រាយការណ៍/ទាក់ទង Admin')
    markup.add(btn1, btn2, btn3, btn4)
    
    bot.reply_to(message, "សូមស្វាគមន៍មកកាន់ Vieki Store! 🛒\nសូមជ្រើសរើសសេវាកម្មខាងក្រោម៖", reply_markup=markup)

# ចាប់យកសារពេលគេចុចលើ Button នីមួយៗ
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if message.text == '👤 គណនីរបស់ខ្ញុំ':
        bot.reply_to(message, f"👤 ឈ្មោះ៖ {message.from_user.first_name}\nID: {message.from_user.id}\nតុល្យភាព៖ $0.00")
    elif message.text == '💳 បញ្ចូលលុយ':
        bot.reply_to(message, "សូមផ្ញើរូបភាពវិក្កយបត្រ ABA ដើម្បីបញ្ចូលទឹកប្រាក់...")
    elif message.text == '🛒 ទិញ Account Blox Fruit':
        bot.reply_to(message, "📦 Account ដែលមានស្ដុក៖\n1. Blox Fruit Lv MAX + Cursed Dual Katana ($5)")
    elif message.text == '🆘 រាយការណ៍/ទាក់ទង Admin':
        bot.reply_to(message, "📞 ទាក់ទង Admin ផ្ទាល់៖ @your_admin_username")
    else:
        bot.reply_to(message, f"អ្នកបានផ្ញើ៖ {message.text}")

print("Bot is starting...")
bot.infinity_polling(skip_pending=True)
