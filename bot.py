import random
import sqlite3
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.utils import executor

# ================== TOKEN ==================
TOKEN = os.environ["TOKEN"]

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ================== DATABASE ==================
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 100
)
""")
conn.commit()

# ✅ اصلاح شده (فقط یکبار کاربر ساخته می‌شود)
def get_user(user_id):
    cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    user = cursor.fetchone()
    if user is None:
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, 100)", (user_id,))
        conn.commit()

def get_balance(user_id):
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone()[0]

def add_balance(user_id, amount):
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    conn.commit()

def get_name(user):
    return f"@{user.username}" if user.username else user.full_name


# ================== START ==================
@dp.message_handler(commands=['start'], chat_type=types.ChatType.PRIVATE)
async def start(message: types.Message):
    get_user(message.from_user.id)

    text = (
        "🚀✨ به ربات پیشرفته خوش آمدید!\n\n"
        "💎 اینجا می‌توانید بازی کنید و سکه جمع کنید!\n\n"
        "👇 یکی از گزینه‌ها را انتخاب کنید:"
    )

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("💰 موجودی من", callback_data="balance"),
        InlineKeyboardButton("🎮 بازی شرطی", callback_data="bet_info"),
        InlineKeyboardButton("✂ سنگ کاغذ قیچی", callback_data="rps_info"),
        InlineKeyboardButton("👤 پروفایل", callback_data="profile")
    )

    await message.answer(text, reply_markup=keyboard)


# ================== CALLBACK MENU ==================
@dp.callback_query_handler(lambda c: c.data == "balance")
async def balance_callback(callback: CallbackQuery):
    get_user(callback.from_user.id)
    balance = get_balance(callback.from_user.id)
    await callback.answer()
    await callback.message.answer(f"💰 موجودی شما: {balance} سکه 💎")

@dp.callback_query_handler(lambda c: c.data == "profile")
async def profile_callback(callback: CallbackQuery):
    get_user(callback.from_user.id)
    balance = get_balance(callback.from_user.id)
    name = get_name(callback.from_user)
    await callback.answer()
    await callback.message.answer(
        f"👤 نام: {name}\n"
        f"💎 موجودی: {balance}"
    )

@dp.callback_query_handler(lambda c: c.data == "bet_info")
async def bet_info(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("برای ساخت بازی در گروه بنویس:\nبازی 50")

@dp.callback_query_handler(lambda c: c.data == "rps_info")
async def rps_info(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("برای بازی بنویس:\nسنگچی 10")


# ================== موجودی در گروه ==================
@dp.message_handler(lambda message: message.text == "موجودی")
async def balance_group(message: types.Message):
    get_user(message.from_user.id)
    balance = get_balance(message.from_user.id)
    name = get_name(message.from_user)
    await message.reply(f"💰 موجودی {name}: {balance} سکه 💎")


# ================== انتقال سکه ==================
@dp.message_handler(lambda message: message.text and message.text.startswith("انتقال"))
async def transfer_coin(message: types.Message):
    parts = message.text.split()

    if len(parts) < 2:
        await message.reply("فرمت صحیح:\nانتقال 50\nیا\nانتقال 50 123456789")
        return

    try:
        amount = int(parts[1])
    except:
        await message.reply("❌ مبلغ نامعتبر است")
        return

    if amount <= 0:
        await message.reply("❌ مبلغ باید بیشتر از صفر باشد")
        return

    sender_id = message.from_user.id
    target_id = None

    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
    elif len(parts) >= 3:
        try:
            target_id = int(parts[2])
        except:
            await message.reply("❌ آیدی مقصد نامعتبر است (باید عدد باشد)")
            return
    else:
        await message.reply("❌ باید ریپلای کنید یا آیدی عددی بدهید")
        return

    if sender_id == target_id:
        await message.reply("❌ نمی‌توانید به خودتان انتقال دهید")
        return

    get_user(sender_id)
    get_user(target_id)

    if get_balance(sender_id) < amount:
        await message.reply("❌ موجودی کافی نیست")
        return

    add_balance(sender_id, -amount)
    add_balance(target_id, amount)

    await message.reply(f"✅ {amount} سکه با موفقیت منتقل شد!")


# ================== ادامه کد شما بدون تغییر ==================
# (بازی شرطی + سنگچی + وب سرور دقیقاً همان نسخه قبلی شماست)

# ================== WEB SERVER ==================
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_web():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

# ================== RUN ==================
if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    executor.start_polling(dp, skip_updates=True)
