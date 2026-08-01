import os
import sqlite3
import shutil
import time
from datetime import datetime
import telebot
from telebot import types

# ==========================================
# 1. CONFIGURATIONS (Environment Variables)
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8654200136:AAGTEmmg3Rb5Z36aGlGrn1j3-36JwzsU-Gs")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6872141480"))
COOLDOWN_TIME = 15 * 60  # 15 minutes Anti-Spam

bot = telebot.TeleBot(BOT_TOKEN)
DB_PATH = 'shop_bot.db'

# ==========================================
# 2. DATABASE SETUP & BACKUP SYSTEM
# ==========================================
def db_connect():
    return sqlite3.connect(DB_PATH, timeout=20)

def init_db():
    with db_connect() as conn:
        cursor = conn.cursor()
        
        # Users Table
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0,
            last_topup_time INTEGER DEFAULT 0
        )''')
        
        # Categories Table
        cursor.execute('''CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            price REAL NOT NULL,
            description TEXT,
            photo_id TEXT
        )''')
        
        # Stock Table
        cursor.execute('''CREATE TABLE IF NOT EXISTS stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name TEXT NOT NULL,
            item_data TEXT NOT NULL,
            is_sold INTEGER DEFAULT 0
        )''')
        
        # History Table
        cursor.execute('''CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            amount REAL,
            item_data TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        # Settings Table
        cursor.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')

        # Default UI Values
        defaults = [
            ('btn_buy', '🛒 ទិញអាខោន'),
            ('btn_profile', '👤 គណនីរបស់ខ្ញុំ'),
            ('btn_topup', '💳 បញ្ចូលលុយ'),
            ('btn_history', '📜 ប្រវត្តិរបស់ខ្ញុំ'),
            ('btn_support', '🆘 រាយការណ៍/ទាក់ទង Admin'),
            ('welcome_msg', 'សួស្តី {first_name}!\nសូមស្វាគមន៍មកកាន់ហាងលក់អាខោន។'),
            ('topup_msg', '💳 **ព័ត៌មានគណនីសម្រាប់បញ្ចូលលុយ**\n\n🏦 **ABA Bank:** `000 111 222` (NAME)\n\n📸 **សូមផ្ញើរូបថតចុងសន្លឹក (Slip ធនាគារ)** បន្ទាប់ពីវេលុយរួច៖'),
            ('topup_qr', '')
        ]
        for k, v in defaults:
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        conn.commit()

def backup_database():
    try:
        now_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"shop_bot_backup_{now_str}.db"
        shutil.copyfile(DB_PATH, backup_filename)
        print(f"✅ Backup successful: {backup_filename}")
    except Exception as e:
        print(f"❌ Backup failed: {e}")

init_db()
backup_database()

# --- HELPER FUNCTIONS ---
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
    """Atomic stock check and purchase to prevent race conditions."""
    with db_connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, item_data FROM stock WHERE category_name = ? AND is_sold = 0 LIMIT 1",
            (category_name,)
        )
        item = cursor.fetchone()
        if not item:
            return None

        item_id, item_data = item
        cursor.execute("UPDATE stock SET is_sold = 1 WHERE id = ? AND is_sold = 0", (item_id,))
        if cursor.rowcount == 0:
            return None

        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (price, user_id))
        conn.commit()

    record_history(user_id, f"ទិញ {category_name}", -price, item_data)
    return item_data

def check_topup_cooldown(user_id):
    with db_connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT last_topup_time FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()

    current_time = int(time.time())
    if not row or not row[0]:
        return True, 0

    elapsed = current_time - row[0]
    if elapsed < COOLDOWN_TIME:
        remaining_min = int((COOLDOWN_TIME - elapsed) // 60) + 1
        return False, remaining_min

    return True, 0

def update_topup_time(user_id):
    with db_connect() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_topup_time = ? WHERE user_id = ?", (int(time.time()), user_id))
        conn.commit()

# ==========================================
# 3. Dynamic User Keyboard
# ==========================================
def build_user_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton(get_setting('btn_buy', '🛒 ទិញអាខោន')),
        types.KeyboardButton(get_setting('btn_profile', '👤 គណនីរបស់ខ្ញុំ'))
    )
    markup.add(
        types.KeyboardButton(get_setting('btn_topup', '💳 បញ្ចូលលុយ')),
        types.KeyboardButton(get_setting('btn_history', '📜 ប្រវត្តិរបស់ខ្ញុំ'))
    )
    markup.add(types.KeyboardButton(get_setting('btn_support', '🆘 រាយការណ៍/ទាក់ទង Admin')))
    return markup

# ==========================================
# 4. USER MENU HANDLERS
# ==========================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    get_user_balance(user_id)
    
    welcome_template = get_setting('welcome_msg', 'សួស្តី {first_name}!\nសូមស្វាគមន៍មកកាន់ហាងលក់អាខោន។')
    welcome_text = welcome_template.format(first_name=message.from_user.first_name)
    bot.send_message(message.chat.id, welcome_text, reply_markup=build_user_keyboard())

@bot.message_handler(func=lambda msg: msg.text == get_setting('btn_buy', '🛒 ទិញអាខោន'))
def handle_buy_btn(message):
    send_catalog_menu(message.chat.id)

@bot.message_handler(func=lambda msg: msg.text == get_setting('btn_profile', '👤 គណនីរបស់ខ្ញុំ'))
def handle_profile_btn(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    bot.send_message(message.chat.id, f"🆔 ID របស់អ្នក: `{user_id}`\n💰 សមតុល្យលុយ: **${balance:.2f}**", parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == get_setting('btn_topup', '💳 បញ្ចូលលុយ'))
def handle_topup_btn(message):
    handle_topup_request(message)

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

    text = "📜 **ប្រវត្តិប្រតិបត្តិការចុងក្រោយរបស់អ្នក (5 ដង):**\n\n"
    for action, amount, item_data, time_str in history:
        symbol = "🟢" if amount > 0 else "🔴"
        text += f"{symbol} **{action}** (${amount:.2f})\n"
        text += f"🕒 ពេល: `{time_str[:16]}`\n"
        if item_data:
            text += f"🔑 **ទិន្នន័យអាខោន/លេខកូដ:** `{item_data}`\n"
        text += "-------------------------------\n"

    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == get_setting('btn_support', '🆘 រាយការណ៍/ទាក់ទង Admin'))
def handle_support_btn(message):
    msg = bot.send_message(message.chat.id, "📝 **សូមវាយបញ្ចូលសារ ឬ បញ្ហាដែលអ្នកជួបប្រទះ៖**\n*(សាររបស់អ្នកនឹងត្រូវផ្ញើត្រង់ទៅកាន់ Admin)*")
    bot.register_next_step_handler(msg, process_report_to_admin)

def process_report_to_admin(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    report_text = message.text

    bot.send_message(
        ADMIN_ID,
        f"📩 **មានសាររាយការណ៍/ទាក់ទងពី Customer!**\n\n👤 អ្នកផ្ញើ: {user_name}\n🆔 ID: `{user_id}`\n💬 សារ: {report_text}",
        parse_mode="Markdown"
    )
    bot.send_message(message.chat.id, "✅ **បានផ្ញើសារទៅកាន់ Admin រួចរាល់!**\nAdmin នឹងពិនិត្យ និងឆ្លើយតបជូនលោកអ្នកឆាប់ៗ។")

def handle_topup_request(message):
    user_id = message.from_user.id
    can_topup, wait_min = check_topup_cooldown(user_id)

    if not can_topup:
        bot.send_message(
            message.chat.id,
            f"⚠️ **ប្រព័ន្ធការពារ Spam!**\n\nអ្នកអាចធ្វើការផ្ញើ Request បញ្ចូលលុយម្តងទៀតបានបន្ទាប់ពី **{wait_min} នាទី** ទៀត។",
            parse_mode="Markdown"
        )
        return

    topup_text = get_setting('topup_msg')
    qr_photo_id = get_setting('topup_qr')

    if qr_photo_id:
        try:
            msg = bot.send_photo(message.chat.id, qr_photo_id, caption=topup_text, parse_mode="Markdown")
        except Exception:
            msg = bot.send_message(message.chat.id, topup_text, parse_mode="Markdown")
    else:
        msg = bot.send_message(message.chat.id, topup_text, parse_mode="Markdown")

    bot.register_next_step_handler(msg, process_slip_upload)

def process_slip_upload(message):
    user_id = message.from_user.id
    if not message.photo:
        bot.send_message(message.chat.id, "❌ សូមផ្ញើជា **រូបថត Slip**!")
        return

    update_topup_time(user_id)
    photo_id = message.photo[-1].file_id
    user_name = message.from_user.first_name

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ យល់ព្រម (Approve)", callback_data=f"app_topup_{user_id}"),
        types.InlineKeyboardButton("❌ បដិសេធ (Reject)", callback_data=f"rej_topup_{user_id}")
    )

    bot.send_photo(
        ADMIN_ID,
        photo_id,
        caption=f"📥 **មានសំណើបញ្ចូលលុយថ្មី!**\n\n👤 អ្នកផ្ញើ: {user_name}\n🆔 User ID: `{user_id}`",
        parse_mode="Markdown",
        reply_markup=markup
    )
    bot.send_message(message.chat.id, "✅ **បានផ្ញើ Slip រួចរាល់!**\nសូមរង់ចាំ Admin ពិនិត្យ។")

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

# ==========================================
# 5. ITEM DETAILS, CONFIRMATION & BUY SYSTEM
# ==========================================

# 1. បង្ហាញព័ត៌មានទំនិញ + ប៊ូតុង "ទិញ" និង "ត្រឡប់ក្រោយ"
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

    text = f"📌 **ប្រភេទ៖** {name}\n"
    text += f"💰 **តម្លៃ៖** ${price:.2f}\n"
    text += f"📦 **ស្តុកនៅសល់៖** {stock_cnt} អាខោន\n"
    if desc:
        text += f"📝 **ព័ត៌មានបន្ថែម៖** {desc}\n"

    markup = types.InlineKeyboardMarkup()
    # ចុចទៅកាន់ដំណាក់កាល Ask Confirmation
    markup.add(types.InlineKeyboardButton("🛒 ទិញឥឡូវនេះ", callback_data=f"ask_buy_{cat_id}"))
    # ប៊ូតុងត្រឡប់ក្រោយទៅកាន់ Catalog Menu
    markup.add(types.InlineKeyboardButton("🔙 ត្រឡប់ក្រោយ", callback_data="back_to_catalog"))

    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

    if photo_id:
        bot.send_photo(call.message.chat.id, photo_id, caption=text, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

# 2. ប៊ូតុងត្រឡប់ក្រោយទៅ Menu ទំនិញដើម
@bot.callback_query_handler(func=lambda call: call.data == "back_to_catalog")
def back_catalog(call):
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    send_catalog_menu(call.message.chat.id)

# 3. ដំណាក់កាលសួរបញ្ជាក់ (Confirm Step - លើកទី ២)
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

    text = f"⚠️ **ការបញ្ជាក់ការទិញ (Confirm Order)**\n\n"
    text += f"📦 ទំនិញ: **{name}**\n"
    text += f"💵 តម្លៃ: **${price:.2f}**\n"
    text += f"💳 សមតុល្យរបស់អ្នក: **${balance:.2f}**\n\n"
    text += "តើអ្នកប្រាកដជាចង់ទិញអាខោននេះមែនទេ?"

    markup = types.InlineKeyboardMarkup()
    # ប៊ូតុងបញ្ជាក់ទិញផ្តាច់ព្រ័ត្រ
    markup.add(types.InlineKeyboardButton("✅ ប្រាកដហើយ (ទិញ)", callback_data=f"confirm_buy_{cat_id}"))
    # ប៊ូតុងបោះបង់ / ត្រឡប់ក្រោយទៅមើលព័ត៌មានទំនិញវិញ
    markup.add(types.InlineKeyboardButton("❌ បោះបង់ / ត្រឡប់ក្រោយ", callback_data=f"view_cat_{cat_id}"))

    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

    bot.send_message(call.message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

# 4. ការទាត់កាត់លុយ និងប្រគល់ទំនិញ (Final Buy Execution)
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
    user_name = call.from_user.first_name
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

    try:
        bot.send_message(
            ADMIN_ID,
            f"🔔 **[REAL-TIME ALERT] មានការទិញអាខោនថ្មី!**\n\n👤 អ្នកទិញ: {user_name}\n🆔 User ID: `{user_id}`\n📦 ប្រភេទ: {name}\n💵 តម្លៃ: ${price:.2f}\n🔑 លេខកូដ: `{item_data}`",
            parse_mode="Markdown"
        )
    except Exception:
        pass

# ==========================================
# 6. ADMIN PANEL & MANAGEMENT
# ==========================================
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
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
    markup.add(types.InlineKeyboardButton("⚙️ កែប្រែ Menu & អត្ថបទ", callback_data="adm_edit_menu"))
    markup.add(types.InlineKeyboardButton("📥 ទាញយក Database Backup", callback_data="adm_download_db"))

    bot.send_message(message.chat.id, "⚙️ **ផ្ទាំងគ្រប់គ្រង ADMIN**", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "adm_download_db")
def send_database_backup(call):
    if call.from_user.id != ADMIN_ID:
        return
    try:
        with open(DB_PATH, 'rb') as doc:
            bot.send_document(
                call.message.chat.id,
                doc,
                caption=f"📦 **Database Backup**\n🕒 កាលបរិច្ឆេទ: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
                parse_mode="Markdown"
            )
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ មិនអាចទាញយក File បានទេ: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "adm_edit_menu")
def admin_edit_menu_options(call):
    if call.from_user.id != ADMIN_ID:
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🖼️ កែប្រែ/ដាក់រូប QR ABA", callback_data="setqr_topup_qr"),
        types.InlineKeyboardButton("🏦 កែប្រែអត្ថបទធនាគារ (Topup Text)", callback_data="setkey_topup_msg"),
        types.InlineKeyboardButton("✏️ កែប្រែប៊ូតុង 'ទិញអាខោន'", callback_data="setkey_btn_buy"),
        types.InlineKeyboardButton("✏️ កែប្រែប៊ូតុង 'គណនីរបស់ខ្ញុំ'", callback_data="setkey_btn_profile"),
        types.InlineKeyboardButton("✏️ កែប្រែប៊ូតុង 'បញ្ចូលលុយ'", callback_data="setkey_btn_topup"),
        types.InlineKeyboardButton("✏️ កែប្រែប៊ូតុង 'ប្រវត្តិរបស់ខ្ញុំ'", callback_data="setkey_btn_history"),
        types.InlineKeyboardButton("✏️ កែប្រែប៊ូតុង 'រាយការណ៍/ទាក់ទង'", callback_data="setkey_btn_support"),
        types.InlineKeyboardButton("📝 កែប្រែសារ Welcome Message", callback_data="setkey_welcome_msg")
    )
    bot.send_message(call.message.chat.id, "🛠 **សូមជ្រើសរើសផ្នែកដែលត្រូវកែប្រែ៖**", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('setkey_'))
def handle_setkey_prompt(call):
    if call.from_user.id != ADMIN_ID:
        return

    key_name = call.data.replace('setkey_', '')
    current_val = get_setting(key_name)

    msg = bot.send_message(
        call.message.chat.id,
        f"📝 **តម្លៃបច្ចុប្បន្ន៖**\n`{current_val}`\n\nសូមផ្ញើ **អត្ថបទថ្មី** ដែលអ្នកចង់ជំនួស៖",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, process_update_setting, key_name)

def process_update_setting(message, key_name):
    new_val = message.text.strip()
    set_setting(key_name, new_val)
    bot.send_message(message.chat.id, f"✅ បានកែប្រែ **{key_name}** ដោយជោគជ័យ!", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "setqr_topup_qr")
def handle_setqr_prompt(call):
    if call.from_user.id != ADMIN_ID:
        return

    msg = bot.send_message(
        call.message.chat.id,
        "🖼️ **សូមផ្ញើរូបថត (Photo) QR Code ABA ថ្មីរបស់អ្នក៖**\n*(ដើម្បីឱ្យប្រព័ន្ធបង្ហាញរូបនេះពេលអតិថិជនចុច 'បញ្ចូលលុយ')*",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, process_update_qr)

def process_update_qr(message):
    if not message.photo:
        bot.send_message(message.chat.id, "❌ សូមផ្ញើជា **រូបថត (Photo)**!")
        return

    photo_id = message.photo[-1].file_id
    set_setting('topup_qr', photo_id)
    bot.send_message(message.chat.id, "✅ **បានប្តូររូប QR Code ABA ដោយជោគជ័យ!**", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith(('app_topup_', 'rej_topup_')))
def handle_slip_approval(call):
    if call.from_user.id != ADMIN_ID:
        return

    action = call.data.split('_')[0]
    target_user = int(call.data.split('_')[2])

    if action == "rej":
        bot.answer_callback_query(call.id, "បានបដិសេធ!", show_alert=True)
        bot.edit_message_caption("❌ **បានបដិសេធ Slip នេះរួចរាល់!**", call.message.chat.id, call.message.message_id)
        bot.send_message(target_user, "❌ **សំណើបញ្ចូលលុយរបស់អ្នកត្រូវបានបដិសេធ!**\nសូមពិនិត្យមើល Slip ឡើងវិញ ឬទាក់ទង Admin។")
    elif action == "app":
        msg = bot.send_message(call.message.chat.id, f"សូមវាយ **ចំនួនលុយ ($)** ដែលត្រូវបញ្ចូលឱ្យ User ID `{target_user}` (ឧ. `5.0`)៖", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_approve_amount, target_user)

def process_approve_amount(message, target_user):
    try:
        amount = float(message.text.strip())
        update_user_balance(target_user, amount, "បញ្ចូលលុយតាម Slip (Approved)")
        new_bal = get_user_balance(target_user)

        bot.send_message(message.chat.id, f"✅ បានបញ្ចូលលុយ **${amount:.2f}** ឱ្យ ID `{target_user}` រួចរាល់!\nសមតុល្យថ្មី: **${new_bal:.2f}**", parse_mode="Markdown")
        bot.send_message(target_user, f"🎉 **បញ្ចូលលុយជោគជ័យ!**\n\n💰 ទទួលបាន: **${amount:.2f}**\n💵 សមតុល្យសរុប: **${new_bal:.2f}**", parse_mode="Markdown")
    except Exception:
        bot.send_message(message.chat.id, "❌ ចំនួនលុយមិនត្រឹមត្រូវ!")

@bot.callback_query_handler(func=lambda call: call.data.startswith('adm_'))
def handle_admin_actions(call):
    if call.from_user.id != ADMIN_ID:
        return

    if call.data == "adm_add_cat":
        msg = bot.send_message(call.message.chat.id, "សូមវាយ **ឈ្មោះប្រភេទទំនិញ** (ឧទាហរណ៍៖ `Telegram_US`)", parse_mode="Markdown")
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

        stats_text = f"📊 **របាយការណ៍ហាងបច្ចុប្បន្ន**\n\n"
        stats_text += f"👥 អតិថិជនសរុប: **{u_cnt} នាក់**\n"
        stats_text += f"✅ លក់ដាច់សរុប: **{sold_cnt} អាខោន**\n"
        stats_text += f"📦 ស្តុកនៅសល់សរុប: **{active_cnt} អាខោន**\n"
        bot.send_message(call.message.chat.id, stats_text, parse_mode="Markdown")

    elif call.data in ["adm_add_bal", "adm_sub_bal"]:
        is_add = (call.data == "adm_add_bal")
        msg = bot.send_message(call.message.chat.id, f"សូមផ្ញើ ID និង ចំនួនលុយ (ឧទាហរណ៍៖ `123456789 10`)", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_admin_balance, is_add)

    elif call.data == "adm_check_his":
        msg = bot.send_message(call.message.chat.id, "សូមផ្ញើ User ID ដើម្បីឆែកមើលប្រវត្តិ (ឧទាហរណ៍៖ `123456789`)")
        bot.register_next_step_handler(msg, process_admin_history)

    elif call.data == "adm_broadcast":
        msg = bot.send_message(call.message.chat.id, "សូមផ្ញើសារ ឬ រូបភាពដែលត្រូវប្រកាសទៅកាន់ User ទាំងអស់៖")
        bot.register_next_step_handler(msg, process_admin_broadcast)

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
            
        txt = f"📜 **ប្រវត្តិប្រតិបត្តិការរបស់ User ID `{uid}`:**\n\n"
        for act, amt, item_data, tm in his:
            symbol = "🟢" if amt > 0 else "🔴"
            txt += f"{symbol} **{act}** (${amt:.2f})\n"
            txt += f"🕒 ពេល: `{tm[:16]}`\n"
            if item_data:
                txt += f"🔑 **ទិន្នន័យអាខោន/លេខកូដ:** `{item_data}`\n"
            txt += "-------------------------------\n"
            
        bot.send_message(message.chat.id, txt, parse_mode="Markdown")
    except Exception:
        bot.send_message(message.chat.id, "❌ ID មិនត្រឹមត្រូវ!")

def process_cat_name(message):
    cat_name = message.text.strip()
    msg = bot.send_message(message.chat.id, f"បញ្ចូល **តម្លៃ ($)** សម្រាប់ {cat_name} (ឧទាហរណ៍៖ `2.5`)", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_cat_price, cat_name)

def process_cat_price(message, cat_name):
    try:
        price = float(message.text.strip())
        msg = bot.send_message(message.chat.id, "បញ្ចូល **ព័ត៌មានបន្ថែម/ការធានា** (ឬវាយ `skip` ដើម្បីរំលង)៖", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_cat_desc, cat_name, price)
    except Exception:
        bot.send_message(message.chat.id, "❌ តម្លៃមិនត្រឹមត្រូវ!")

def process_cat_desc(message, cat_name, price):
    desc = None if message.text and message.text.lower() == 'skip' else message.text
    msg = bot.send_message(message.chat.id, "សូម **ផ្ញើរូបភាព (Photo)** សម្រាប់ប្រភេទទំនិញនេះ (ឬវាយ `skip` បើមិនដាក់រូប)៖")
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
        bot.send_message(message.chat.id, "❌ ខុសទម្រង់! (ឧទាហរណ៍៖ `123456789 10`)")

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
# 7. BOT EXECUTION LOOP
# ==========================================
if __name__ == '__main__':
    print("🚀 Bot is running...")
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            print(f"❌ Connection error: {e}")
            time.sleep(5)
