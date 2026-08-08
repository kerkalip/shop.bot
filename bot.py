import os
import sqlite3
import shutil
import time
import threading
from datetime import datetime
import requests
from flask import Flask
import telebot
from telebot import types
from khqr import KHQR

# ==========================================
# 1. CONFIGURATIONS
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8654200136:AAGTEmmg3Rb5Z36aGlGrn1j3-36JwzsU-Gs")

# កំណត់ ID Admin ទាំង ២ នាក់
admin_env = os.getenv("ADMIN_ID", "6872141480, 987654321")
ADMIN_IDS = [int(i.strip()) for i in admin_env.split(",") if i.strip().isdigit()]

# Bakong Developer API Settings
BAKONG_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjp7ImlkIjoiMWQwM2I1Mzk5NTE5NDFjNiJ9LCJpYXQiOjE3ODYxMTg0MzksImV4cCI6MTc5Mzg5NDQzOX0.E-RpooCYoToWWsrmPbcgv4pDqPHQk6dGJVrlMu9yjS8"
BAKONG_ACCOUNT_ID = os.getenv("BAKONG_ACCOUNT_ID", "your_account@aba")  # ឧ. sokha@aba ឬ 85512345678@vattana
MERCHANT_NAME = "Vieki Store"
MERCHANT_CITY = "Phnom Penh"

khqr_instance = KHQR()
bot = telebot.TeleBot(BOT_TOKEN)
DB_PATH = 'shop_bot.db'

# ==========================================
# 2. DUMMY WEB SERVER FOR RENDER (Keep-Alive)
# ==========================================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Vieki Store Bot is Alive & Running!"

def run_web_server():
    port = int(os.getenv("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# ==========================================
# 3. HELPER FUNCTIONS & NOTIFICATIONS
# ==========================================
def notify_all_admins(text=None, photo_id=None, reply_markup=None):
    for admin_id in ADMIN_IDS:
        try:
            if photo_id:
                bot.send_photo(admin_id, photo_id, caption=text, parse_mode="Markdown", reply_markup=reply_markup)
            else:
                bot.send_message(admin_id, text, parse_mode="Markdown", reply_markup=reply_markup)
        except Exception:
            pass

# ==========================================
# 4. DATABASE SETUP
# ==========================================
def db_connect():
    return sqlite3.connect(DB_PATH, timeout=20)

def init_db():
    with db_connect() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            price REAL NOT NULL,
            description TEXT,
            photo_id TEXT
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name TEXT NOT NULL,
            item_data TEXT NOT NULL,
            is_sold INTEGER DEFAULT 0
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            amount REAL,
            item_data TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')

        # បញ្ជី Transaction MD5 ដែលបានបង់រួចដើម្បីកុំឱ្យបូកលុយស្ទួន (Prevent Double Topup)
        cursor.execute('''CREATE TABLE IF NOT EXISTS bakong_payments (
            md5 TEXT PRIMARY KEY,
            user_id INTEGER,
            amount REAL,
            status TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        defaults = [
            ('btn_buy', '🛒 ទិញអាខោន'),
            ('btn_profile', '👤 គណនីរបស់ខ្ញុំ'),
            ('btn_topup', '💳 បញ្ចូលលុយ (KHQR)'),
            ('btn_history', '📜 ប្រវត្តិរបស់ខ្ញុំ'),
            ('btn_support', '🆘 រាយការណ៍/ទាក់ទង Admin'),
            ('welcome_msg', 'សួស្តី {first_name}!\nសូមស្វាគមន៍មកកាន់ Vieki Store។')
        ]
        for k, v in defaults:
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        conn.commit()

init_db()

def get_setting(key, default=""):
    with db_connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default

def set_setting(key, value):
    with db_connect() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()

def get_user_balance(user_id):
    with db_connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return row[0]
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, 0.0)", (user_id,))
        conn.commit()
        return 0.0

def record_history(user_id, action, amount, item_data=""):
    with db_connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO history (user_id, action, amount, item_data) VALUES (?, ?, ?, ?)",
            (user_id, action, amount, item_data)
        )
        conn.commit()

def update_user_balance(user_id, amount, action_type="", item_data=""):
    with db_connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, 0.0)", (user_id,))
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
    
    act_name = action_type if action_type else ("Top-up" if amount > 0 else "Deduct")
    record_history(user_id, act_name, amount, item_data)

def get_stock_count(category_name):
    with db_connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM stock WHERE category_name = ? AND is_sold = 0", (category_name,))
        return cursor.fetchone()[0]

def buy_account_item(user_id, category_name, price):
    with db_connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, item_data FROM stock WHERE category_name = ? AND is_sold = 0 LIMIT 1", (category_name,))
        item = cursor.fetchone()
        if not item:
            return None

        item_id, item_data = item
        cursor.execute("UPDATE stock SET is_sold = 1 WHERE id = ?", (item_id,))
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (price, user_id))
        conn.commit()

    record_history(user_id, f"ទិញ {category_name}", -price, item_data)
    return item_data

# ==========================================
# 5. BAKONG KHQR API INTEGRATION
# ==========================================
def generate_khqr_data(amount_usd):
    try:
        qr_data = khqr_instance.create_individual(
            bakong_account_id=BAKONG_ACCOUNT_ID,
            account_name=MERCHANT_NAME,
            merchant_city=MERCHANT_CITY,
            amount=float(amount_usd),
            currency="USD",
            store_label=MERCHANT_NAME,
            terminal_label="TelegramBot"
        )
        qr_string = qr_data.get('data', {}).get('qr')
        md5_hash = qr_data.get('data', {}).get('md5')
        return qr_string, md5_hash
    except Exception as e:
        print(f"❌ Error Generating KHQR: {e}")
        return None, None

def check_bakong_transaction_md5(md5_hash):
    url = "https://api-bakong.nbc.gov.kh/v1/check_transaction_by_md5"
    headers = {
        'Authorization': f'Bearer {BAKONG_TOKEN}',
        'Content-Type': 'application/json'
    }
    payload = {"md5": md5_hash}
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        res_json = res.json()
        if res_json.get("responseCode") == 0 and res_json.get("data"):
            return True, res_json.get("data")
        return False, None
    except Exception as e:
        print(f"❌ Bakong API Check Error: {e}")
        return False, None

# ==========================================
# 6. DYNAMIC KEYBOARD & USER HANDLERS
# ==========================================
def build_user_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton(get_setting('btn_buy', '🛒 ទិញអាខោន')),
        types.KeyboardButton(get_setting('btn_profile', '👤 គណនីរបស់ខ្ញុំ'))
    )
    markup.add(
        types.KeyboardButton(get_setting('btn_topup', '💳 បញ្ចូលលុយ (KHQR)')),
        types.KeyboardButton(get_setting('btn_history', '📜 ប្រវត្តិរបស់ខ្ញុំ'))
    )
    markup.add(types.KeyboardButton(get_setting('btn_support', '🆘 រាយការណ៍/ទាក់ទង Admin')))
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    get_user_balance(message.from_user.id)
    welcome_template = get_setting('welcome_msg', 'សួស្តី {first_name}!\nសូមស្វាគមន៍មកកាន់ Vieki Store។')
    welcome_text = welcome_template.format(first_name=message.from_user.first_name)
    bot.send_message(message.chat.id, welcome_text, reply_markup=build_user_keyboard())

@bot.message_handler(func=lambda msg: msg.text == get_setting('btn_buy', '🛒 ទិញអាខោន'))
def handle_buy_btn(message):
    send_catalog_menu(message.chat.id)

@bot.message_handler(func=lambda msg: msg.text == get_setting('btn_profile', '👤 គណនីរបស់ខ្ញុំ'))
def handle_profile_btn(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    bot.send_message(message.chat.id, f"🆔 **ID របស់អ្នក:** `{user_id}`\n💰 **សមតុល្យលុយ:** **${balance:.2f}**", parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == get_setting('btn_history', '📜 ប្រវត្តិរបស់ខ្ញុំ'))
def handle_history_btn(message):
    user_id = message.from_user.id
    with db_connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT action, amount, item_data, timestamp FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user_id,))
        history = cursor.fetchall()

    if not history:
        bot.send_message(message.chat.id, "មិនទាន់មានប្រវត្តិប្រតិបត្តិការនៅឡើយទេ។")
        return

    text = "📜 **ប្រវត្តិប្រតិបត្តិការចុងក្រោយរបស់អ្នក:**\n\n"
    for action, amount, item_data, time_str in history:
        symbol = "🟢" if amount > 0 else "🔴"
        text += f"{symbol} **{action}** (${amount:.2f})\n"
        text += f"🕒 ពេល: `{time_str[:16]}`\n"
        if item_data:
            text += f"🔑 **ទិន្នន័យ:** `{item_data}`\n"
        text += "-------------------------------\n"

    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == get_setting('btn_support', '🆘 រាយការណ៍/ទាក់ទង Admin'))
def handle_support_btn(message):
    msg = bot.send_message(message.chat.id, "📝 **សូមវាយបញ្ចូលសារ ឬ បញ្ហាដែលអ្នកជួបប្រទះ៖**\n*(សាររបស់អ្នកនឹងត្រូវផ្ញើត្រង់ទៅកាន់ Admin)*")
    bot.register_next_step_handler(msg, process_report_to_admin)

def process_report_to_admin(message):
    notify_all_admins(f"📩 **សារពី Customer:**\n👤 អ្នកផ្ញើ: {message.from_user.first_name}\n🆔 ID: `{message.from_user.id}`\n💬 សារ: {message.text}")
    bot.send_message(message.chat.id, "✅ **បានផ្ញើសារទៅកាន់ Admin រួចរាល់!**")

# ==========================================
# 7. AUTO TOP-UP SYSTEM WITH BAKONG KHQR
# ==========================================
@bot.message_handler(func=lambda msg: msg.text == get_setting('btn_topup', '💳 បញ្ចូលលុយ (KHQR)'))
def handle_topup_btn(message):
    msg = bot.send_message(message.chat.id, "💵 **សូមវាយបញ្ចូលចំនួនទឹកប្រាក់ដែលចង់បញ្ចូលជា ($ USD):**\n*(ឧទាហរណ៍៖ `1.5` ឬ `5`)*", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_topup_amount)

def process_topup_amount(message):
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            bot.send_message(message.chat.id, "❌ ចំនួនទឹកប្រាក់ត្រូវតែធំជាង 0!")
            return

        # Generate KHQR String & MD5
        qr_string, md5_hash = generate_khqr_data(amount)
        if not qr_string or not md5_hash:
            bot.send_message(message.chat.id, "❌ មានបញ្ហាក្នុងការបង្កើត KHQR Code! សូមព្យាយាមម្តងទៀត។")
            return

        # បង្កើត QR Code Image
        qr_photo_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={qr_string}"

        text = f"💳 **ការបញ្ចូលលុយតាម Bakong KHQR**\n\n"
        text += f"💵 ចំនួនទឹកប្រាក់: **${amount:.2f}**\n"
        text += f"🏦 គណនីទទួល: `{BAKONG_ACCOUNT_ID}`\n\n"
        text += "📸 **សូម Scan រូប QR Code ខាងលើដើម្បីស្កេនបង់ប្រាក់តាម App ធនាគារណាក៏បាន។**\n"
        text += "បន្ទាប់ពីបង់ប្រាក់រួចរាល់ សូមចុចប៊ូតុង **[ ✅ ខ្ញុំបានបង់ប្រាក់រួចរាល់ ]** ខាងក្រោមដើម្បីឱ្យប្រព័ន្ធបូកលុយស្វ័យប្រវត្តិ។"

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ ខ្ញុំបានបង់ប្រាក់រួចរាល់", callback_data=f"check_pay_{md5_hash}_{amount}"))

        bot.send_photo(message.chat.id, qr_photo_url, caption=text, parse_mode="Markdown", reply_markup=markup)

    except ValueError:
        bot.send_message(message.chat.id, "❌ សូមបញ្ចូលចំនួនទឹកប្រាក់ជាលេខឱ្យបានត្រឹមត្រូវ!")

@bot.callback_query_handler(func=lambda call: call.data.startswith('check_pay_'))
def handle_check_payment_callback(call):
    parts = call.data.split('_')
    md5_hash = parts[2]
    amount = float(parts[3])
    user_id = call.from_user.id
    user_name = call.from_user.first_name

    # ឆែកមើលក្រែងលោ Transaction MD5 នេះធ្លាប់បានបូកលុយរួចហើយ
    with db_connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM bakong_payments WHERE md5 = ?", (md5_hash,))
        already = cursor.fetchone()

    if already and already[0] == 'SUCCESS':
        bot.answer_callback_query(call.id, "⚠️ Transaction នេះបានបូកលុយរួចរាល់ហើយ!", show_alert=True)
        return

    # ឆែកមើលប្រព័ន្ធ Bakong API
    is_success, pay_data = check_bakong_transaction_md5(md5_hash)

    if is_success:
        # កត់ត្រា និងបូកលុយស្វ័យប្រវត្តិ
        with db_connect() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO bakong_payments (md5, user_id, amount, status) VALUES (?, ?, ?, 'SUCCESS')", (md5_hash, user_id, amount))
            conn.commit()

        update_user_balance(user_id, amount, "Auto Top-up (Bakong KHQR)")
        new_bal = get_user_balance(user_id)

        bot.answer_callback_query(call.id, "🎉 បង់ប្រាក់ជោគជ័យ!")
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass

        bot.send_message(
            call.message.chat.id,
            f"🎉 **បញ្ចូលលុយជោគជ័យ (Auto Top-up)!**\n\n💰 ទទួលបាន: **${amount:.2f}**\n💵 សមតុល្យសរុបថ្មី: **${new_bal:.2f}**\n\nអរគុណសម្រាប់ការគាំទ្រ!",
            parse_mode="Markdown"
        )

        # ផ្ញើ Alert ជូន Admin ទាំង ២ នាក់
        notify_all_admins(
            f"🔔 **[AUTO TOP-UP ALERT]**\n\n👤 អតិថិជន: {user_name}\n🆔 User ID: `{user_id}`\n💵 ចំនួនលុយ: **${amount:.2f}**\n🔑 MD5: `{md5_hash}`"
        )
    else:
        bot.answer_callback_query(call.id, "❌ ប្រព័ន្ធមិនទាន់ទទួលបានការទូទាត់ទេ! សូមបង់ប្រាក់រួចរាល់សិន រួចចុចម្តងទៀត។", show_alert=True)

# ==========================================
# 8. CATALOG & BUY SYSTEM
# ==========================================
def send_catalog_menu(chat_id):
    with db_connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, price FROM categories")
        categories = cursor.fetchall()

    if not categories:
        bot.send_message(chat_id, "មិនទាន់មានទំនិញក្នុងប្រព័ន្ធនៅឡើយទេ។")
        return

    markup = types.InlineKeyboardMarkup()
    for cat_id, name, price in categories:
        stock_cnt = get_stock_count(name)
        btn_text = f"{name} - ${price:.2f} (ស្តុក: {stock_cnt})"
        markup.add(types.InlineKeyboardButton(text=btn_text, callback_data=f"view_cat_{cat_id}"))

    bot.send_message(chat_id, "🛒 **សូមជ្រើសរើសប្រភេទអាខោនដែលអ្នកចង់ទិញ៖**", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('view_cat_'))
def view_category_details(call):
    cat_id = int(call.data.split('_')[2])
    with db_connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, price, description, photo_id FROM categories WHERE id = ?", (cat_id,))
        cat = cursor.fetchone()

    if not cat:
        bot.answer_callback_query(call.id, "រកមិនឃើញប្រភេទទំនិញនេះទេ!", show_alert=True)
        return

    name, price, desc, photo_id = cat
    stock_cnt = get_stock_count(name)

    text = f"📌 **ប្រភេទ៖** {name}\n💰 **តម្លៃ៖** ${price:.2f}\n📦 **ស្តុកនៅសល់៖** {stock_cnt} អាខោន\n"
    if desc:
        text += f"📝 **ព័ត៌មានបន្ថែម៖** {desc}\n"

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🛒 ទិញឥឡូវនេះ", callback_data=f"ask_buy_{cat_id}"))
    markup.add(types.InlineKeyboardButton("🔙 ត្រឡប់ក្រោយ", callback_data="back_to_catalog"))

    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

    if photo_id:
        bot.send_photo(call.message.chat.id, photo_id, caption=text, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_catalog")
def back_catalog(call):
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    send_catalog_menu(call.message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('ask_buy_'))
def ask_buy_confirmation(call):
    cat_id = int(call.data.split('_')[2])
    with db_connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, price FROM categories WHERE id = ?", (cat_id,))
        cat = cursor.fetchone()

    if not cat:
        bot.answer_callback_query(call.id, "ទំនិញមិនត្រឹមត្រូវ!", show_alert=True)
        return

    name, price = cat
    user_id = call.from_user.id
    balance = get_user_balance(user_id)

    if balance < price:
        bot.answer_callback_query(call.id, f"⚠️ លុយមិនគ្រប់គ្រាន់ទេ! អ្នកមាន ${balance:.2f} ប៉ុណ្ណោះ។", show_alert=True)
        return

    text = f"⚠️ **ការបញ្ជាក់ការទិញ (Confirm Order)**\n\n📦 ទំនិញ: **{name}**\n💵 តម្លៃ: **${price:.2f}**\n💳 សមតុល្យរបស់អ្នក: **${balance:.2f}**\n\nតើអ្នកប្រាកដជាចង់ទិញអាខោននេះមែនទេ?"

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ ប្រាកដហើយ (ទិញ)", callback_data=f"confirm_buy_{cat_id}"))
    markup.add(types.InlineKeyboardButton("❌ បោះបង់ / ត្រឡប់ក្រោយ", callback_data=f"view_cat_{cat_id}"))

    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

    bot.send_message(call.message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_buy_'))
def handle_final_purchase(call):
    cat_id = int(call.data.split('_')[2])
    with db_connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, price FROM categories WHERE id = ?", (cat_id,))
        cat = cursor.fetchone()

    if not cat:
        bot.answer_callback_query(call.id, "ទំនិញមិនត្រឹមត្រូវ!", show_alert=True)
        return

    name, price = cat
    user_id = call.from_user.id
    balance = get_user_balance(user_id)

    if balance < price:
        bot.answer_callback_query(call.id, "លុយមិនគ្រប់គ្រាន់ទេ!", show_alert=True)
        return

    item_data = buy_account_item(user_id, name, price)
    if not item_data:
        bot.answer_callback_query(call.id, "សុំទោស អាខោននេះអស់ពីស្តុកហើយ!", show_alert=True)
        return

    new_bal = get_user_balance(user_id)
    bot.answer_callback_query(call.id, "ទិញជោគជ័យ!")

    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

    bot.send_message(
        call.message.chat.id,
        f"✅ **ទិញជោគជ័យ!**\n\n📦 **ប្រភេទ:** {name}\n🔑 **ទិន្នន័យអាខោន/លេខកូដ:** `{item_data}`\n💰 **សមតុល្យនៅសល់:** ${new_bal:.2f}",
        parse_mode="Markdown"
    )

    notify_all_admins(
        f"🔔 **[REAL-TIME ALERT] មានការទិញអាខោន!**\n\n👤 អ្នកទិញ: {call.from_user.first_name}\n🆔 User ID: `{user_id}`\n📦 ប្រភេទ: {name}\n💵 តម្លៃ: ${price:.2f}\n🔑 លេខកូដ: `{item_data}`"
    )

# ==========================================
# 9. ADMIN PANEL & MANAGEMENT
# ==========================================
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS:
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ បង្កើតប្រភេទទំនិញ", callback_data="adm_add_cat"),
        types.InlineKeyboardButton("📦 បន្ថែមស្តុក (Bulk)", callback_data="adm_add_stock")
    )
    markup.add(
        types.InlineKeyboardButton("🗑️ លុបប្រភេទទំនិញ", callback_data="adm_del_cat"),
        types.InlineKeyboardButton("📊 របាយការណ៍ហាង", callback_data="adm_stats")
    )
    markup.add(
        types.InlineKeyboardButton("➕ បញ្ចូលលុយ User", callback_data="adm_add_bal"),
        types.InlineKeyboardButton("➖ ដកលុយ User", callback_data="adm_sub_bal")
    )
    markup.add(
        types.InlineKeyboardButton("📜 ឆែកប្រវត្តិ User", callback_data="adm_check_his"),
        types.InlineKeyboardButton("📢 ផ្ញើសារប្រកាស", callback_data="adm_broadcast")
    )

    bot.send_message(message.chat.id, "⚙️ **ផ្ទាំងគ្រប់គ្រង ADMIN**", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('adm_'))
def handle_admin_actions(call):
    if call.from_user.id not in ADMIN_IDS:
        return

    if call.data == "adm_add_cat":
        msg = bot.send_message(call.message.chat.id, "សូមវាយ **ឈ្មោះប្រភេទទំនិញ** (ឧ. `Blox_Fruit_Acc`)", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_cat_name)

    elif call.data == "adm_add_stock":
        with db_connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM categories")
            cats = cursor.fetchall()

        if not cats:
            bot.send_message(call.message.chat.id, "សូមបង្កើតប្រភេទទំនិញសិន!")
            return

        markup = types.InlineKeyboardMarkup()
        for cid, cname in cats:
            markup.add(types.InlineKeyboardButton(cname, callback_data=f"stk_select_{cname}"))
        bot.send_message(call.message.chat.id, "សូមជ្រើសរើសប្រភេទទំនិញដែលត្រូវបញ្ចូលស្តុក៖", reply_markup=markup)

    elif call.data == "adm_del_cat":
        with db_connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM categories")
            cats = cursor.fetchall()

        markup = types.InlineKeyboardMarkup()
        for cid, cname in cats:
            markup.add(types.InlineKeyboardButton(f"❌ លុប {cname}", callback_data=f"delcat_{cid}"))
        bot.send_message(call.message.chat.id, "ជ្រើសរើសប្រភេទទំនិញដែលត្រូវលុប៖", reply_markup=markup)

    elif call.data == "adm_stats":
        with db_connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            u_cnt = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM stock WHERE is_sold = 1")
            sold_cnt = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM stock WHERE is_sold = 0")
            active_cnt = cursor.fetchone()[0]

        stats_text = f"📊 **របាយការណ៍ហាងបច្ចុប្បន្ន**\n\n👥 អតិថិជនសរុប: **{u_cnt} នាក់**\n✅ លក់ដាច់សរុប: **{sold_cnt} អាខោន**\n📦 ស្តុកនៅសល់សរុប: **{active_cnt} អាខោន**\n"
        bot.send_message(call.message.chat.id, stats_text, parse_mode="Markdown")

    elif call.data in ["adm_add_bal", "adm_sub_bal"]:
        is_add = (call.data == "adm_add_bal")
        msg = bot.send_message(call.message.chat.id, f"សូមផ្ញើ ID និង ចំនួនលុយ (ឧ. `123456789 10`)", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_admin_balance, is_add)

    elif call.data == "adm_check_his":
        msg = bot.send_message(call.message.chat.id, "សូមផ្ញើ User ID ដើម្បីឆែកមើលប្រវត្តិ (ឧ. `123456789`)")
        bot.register_next_step_handler(msg, process_admin_history)

    elif call.data == "adm_broadcast":
        msg = bot.send_message(call.message.chat.id, "សូមផ្ញើសារ ឬ រូបភាពដែលត្រូវប្រកាសទៅកាន់ User ទាំងអស់៖")
        bot.register_next_step_handler(msg, process_admin_broadcast)

def process_cat_name(message):
    cat_name = message.text.strip()
    msg = bot.send_message(message.chat.id, f"បញ្ចូល **តម្លៃ ($)** សម្រាប់ {cat_name} (ឧ. `2.5`)", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_cat_price, cat_name)

def process_cat_price(message, cat_name):
    try:
        price = float(message.text.strip())
        msg = bot.send_message(message.chat.id, "បញ្ចូល **ព័ត៌មានបន្ថែម** (ឬវាយ `skip` ដើម្បីរំលង)៖", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_cat_desc, cat_name, price)
    except Exception:
        bot.send_message(message.chat.id, "❌ តម្លៃមិនត្រឹមត្រូវ!")

def process_cat_desc(message, cat_name, price):
    desc = None if message.text and message.text.lower() == 'skip' else message.text
    msg = bot.send_message(message.chat.id, "សូម **ផ្ញើរូបភាព (Photo)** សម្រាប់ទំនិញ (ឬវាយ `skip` បើមិនដាក់)៖")
    bot.register_next_step_handler(msg, process_cat_photo, cat_name, price, desc)

def process_cat_photo(message, cat_name, price, desc):
    photo_id = message.photo[-1].file_id if message.photo else None
    try:
        with db_connect() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO categories (name, price, description, photo_id) VALUES (?, ?, ?, ?)", (cat_name, price, desc, photo_id))
            conn.commit()
        bot.send_message(message.chat.id, f"✅ បានបង្កើតប្រភេទទំនិញ **{cat_name}** តម្លៃ **${price:.2f}** រួចរាល់!", parse_mode="Markdown")
    except Exception:
        bot.send_message(message.chat.id, "❌ មានបញ្ហា៖ ឈ្មោះទំនិញនេះអាចជាន់គ្នា។")

@bot.callback_query_handler(func=lambda call: call.data.startswith('stk_select_'))
def handle_stock_select(call):
    cname = call.data.replace('stk_select_', '')
    msg = bot.send_message(call.message.chat.id, f"សូមផ្ញើ **ទិន្នន័យអាខោន** សម្រាប់ {cname}៖\n*(1 ជួរ = 1 អាខោន)*", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_bulk_stock, cname)

def process_bulk_stock(message, cname):
    if not message.text:
        bot.send_message(message.chat.id, "❌ ទិន្នន័យត្រូវតែជា Text!")
        return
    items = [line.strip() for line in message.text.strip().split('\n') if line.strip()]
    if not items:
        bot.send_message(message.chat.id, "❌ មិនមានទិន្នន័យ!")
        return

    with db_connect() as conn:
        cursor = conn.cursor()
        for item in items:
            cursor.execute("INSERT INTO stock (category_name, item_data) VALUES (?, ?)", (cname, item))
        conn.commit()

    bot.send_message(message.chat.id, f"✅ បានបញ្ចូលស្តុកចំនួន **{len(items)} អាខោន** ទៅក្នុង **{cname}** រួចរាល់!", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('delcat_'))
def handle_del_cat(call):
    cid = int(call.data.split('_')[1])
    with db_connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM categories WHERE id = ?", (cid,))
        row = cursor.fetchone()
        if row:
            cname = row[0]
            cursor.execute("DELETE FROM categories WHERE id = ?", (cid,))
            cursor.execute("DELETE FROM stock WHERE category_name = ?", (cname,))
            conn.commit()
            bot.answer_callback_query(call.id, f"បានលុប {cname} រួចរាល់!", show_alert=True)

def process_admin_balance(message, is_add):
    try:
        uid, amt = message.text.split()
        uid, amt = int(uid), float(amt)
        final_amt = amt if is_add else -amt
        update_user_balance(uid, final_amt, "Admin បញ្ចូលលុយ" if is_add else "Admin ដកលុយ")
        new_b = get_user_balance(uid)
        bot.send_message(message.chat.id, f"✅ រួចរាល់! សមតុល្យថ្មីរបស់ `{uid}` គឺ **${new_b:.2f}**", parse_mode="Markdown")
    except Exception:
        bot.send_message(message.chat.id, "❌ ខុសទម្រង់! (ឧ. `123456789 10`)")

def process_admin_history(message):
    try:
        uid = int(message.text.strip())
        with db_connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT action, amount, item_data, timestamp FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 10", (uid,))
            his = cursor.fetchall()
            
        if not his:
            bot.send_message(message.chat.id, f"មិនមានប្រវត្តិសម្រាប់ ID `{uid}` ទេ!", parse_mode="Markdown")
            return
            
        txt = f"📜 **ប្រវត្តិរបស់ User ID `{uid}`:**\n\n"
        for act, amt, item_data, tm in his:
            symbol = "🟢" if amt > 0 else "🔴"
            txt += f"{symbol} **{act}** (${amt:.2f})\n"
            txt += f"🕒 ពេល: `{tm[:16]}`\n"
            if item_data:
                txt += f"🔑 **ទិន្នន័យ:** `{item_data}`\n"
            txt += "-------------------------------\n"
            
        bot.send_message(message.chat.id, txt, parse_mode="Markdown")
    except Exception:
        bot.send_message(message.chat.id, "❌ ID មិនត្រឹមត្រូវ!")

def process_admin_broadcast(message):
    with db_connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()

    success, failed = 0, 0
    for (u_id,) in users:
        try:
            bot.copy_message(chat_id=u_id, from_chat_id=message.chat.id, message_id=message.message_id)
            success += 1
        except Exception:
            failed += 1

    bot.send_message(message.chat.id, f"📢 **ប្រកាសរួចរាល់!**\n\n✅ ជោគជ័យ: {success} នាក់\n❌ បរាជ័យ: {failed} នាក់", parse_mode="Markdown")

# ==========================================
# 10. BOT EXECUTION LOOP
# ==========================================
if __name__ == '__main__':
    # 1. Start Flask Web Server
    server_thread = threading.Thread(target=run_web_server)
    server_thread.daemon = True
    server_thread.start()

    # 2. Clear Webhook to prevent Conflict Error 409
    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception as e:
        print(f"Webhook clear status: {e}")

    print("🚀 Bot is running with Auto Top-up...")
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
        except Exception as e:
            print(f"❌ Connection error: {e}")
            time.sleep(5)
