import telebot
from telebot import types

TOKEN = '8654200136:AAGTEmmg3Rb5Z36aGlGrn1j3-36JwzsU-Gs'
bot = telebot.TeleBot(TOKEN)

# ១. ពេលចុច /start ឱ្យបង្ហាញ ប៊ូតុង/Menu
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn1 = types.KeyboardButton('👤 គណនីរបស់ខ្ញុំ')
    btn2 = types.KeyboardButton('💳 បញ្ចូលលុយ')
    btn3 = types.KeyboardButton('🛒 ទិញ Account')
    btn4 = types.KeyboardButton('🆘 រាយការណ៍/ទាក់ទង Admin')
    markup.add(btn1, btn2, btn3, btn4)
    
    bot.reply_to(
        message, 
        f"សួស្តី {message.from_user.first_name}! 🛒\nសូមស្វាគមន៍មកកាន់ Vieki Store!\nសូមជ្រើសរើសMenuខាងក្រោម៖", 
        reply_markup=markup
    )

# ២. ចាប់យកពាក្យដែលគេចុច ដើម្បីឆ្លើយតបឱ្យត្រូវ
@bot.message_handler(func=lambda message: True)
def handle_menu(message):
    text = message.text

    if 'គណនីរបស់ខ្ញុំ' in text:
        bot.reply_to(
            message, 
            f"👤 **ព័ត៌មានគណនី**\n"
            f"• ឈ្មោះ៖ {message.from_user.first_name}\n"
            f"• Telegram ID: `{message.from_user.id}`\n"
            f"• តុល្យភាព៖ **$0.00**",
            parse_mode='Markdown'
        )
    elif 'បញ្ចូលលុយ' in text:
        bot.reply_to(
            message, 
            "💳 **វិធីបញ្ចូលទឹកប្រាក់**\n\n"
            "សូមផ្ញើប្រាក់មកកាន់ ABA៖ `123 456 789` (Vieki Store)\n"
            "រួចផ្ញើរូបភាពវិក្កយបត្រ (Receipt) មកកាន់ទីនេះ!",
            parse_mode='Markdown'
        )
    elif 'ទិញ Account' in text:
        bot.reply_to(
            message, 
            "📦 **បញ្ជី Account ក្នុងស្តុក៖**\n\n"
            "1. Blox Fruit Lv MAX + CDK - **$5.00**\n"
            "2. Blox Fruit Godhuman + Dough V2 - **$8.00**\n\n"
            "_(ទាក់ទង Admin ដើម្បីបញ្ជាទិញ)_"
        )
    elif 'រាយការណ៍' in text or 'Admin' in text:
        bot.reply_to(
            message, 
            "🆘 **ផ្នែកជំនួយ / ទំនាក់ទំនង Admin**\n\n"
            "បើមានបញ្ហា ឬចង់ទិញ Account ផ្ទាល់ សូមទាក់ទង៖\n"
            "👉 Admin: @your_admin_username"
        )
    else:
        bot.reply_to(message, "សូមជ្រើសរើស Menu ខាងក្រោម ឬវាយ /start ឡើងវិញ!")

print("Bot is starting...")
bot.infinity_polling(skip_pending=True)
