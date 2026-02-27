import random
import sqlite3
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from aiogram.utils import executor

# ================== تنظیمات ==================

TOKEN = os.environ["TOKEN"]

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ================== دیتابیس ==================

conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 100
)
""")
conn.commit()

def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()

def get_balance(user_id):
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone()[0]

def get_display_name(user: types.User):
    if user.username:
        return f"@{user.username}"
    return user.full_name

# ================== کیبورد پیوی ==================

def main_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("💰 موجودی من"))
    return keyboard

# ================== حافظه بازی‌ها ==================

waiting_games = {}

# ================== START (فقط پیوی) ==================

@dp.message_handler(commands=['start'], chat_type=types.ChatType.PRIVATE)
async def start(message: types.Message):
    get_user(message.from_user.id)

    await message.answer(
        "🎮 به ربات خوش آمدی!\n"
        "از دکمه زیر برای مشاهده موجودی استفاده کن 👇",
        reply_markup=main_keyboard()
    )

# ================== موجودی (فقط پیوی) ==================

@dp.message_handler(lambda message: message.text == "💰 موجودی من", chat_type=types.ChatType.PRIVATE)
async def balance_private(message: types.Message):
    get_user(message.from_user.id)
    balance = get_balance(message.from_user.id)
    name = get_display_name(message.from_user)

    await message.answer(
        f"💰 موجودی شما:\n\n"
        f"👤 {name}\n"
        f"💎 {balance} سکه"
    )

# ================== ساخت بازی (گروه) ==================

@dp.message_handler(lambda message: message.text and message.text.startswith("بازی"))
async def game(message: types.Message):

    if message.chat.type == "private":
        return

    try:
        amount = int(message.text.split()[1])
    except:
        await message.reply("فرمت صحیح:\nبازی 50")
        return

    if amount <= 0:
        await message.reply("❌ مبلغ باید بیشتر از صفر باشد")
        return

    get_user(message.from_user.id)
    balance = get_balance(message.from_user.id)

    if balance < amount:
        await message.reply("❌ موجودی کافی نیست")
        return

    if amount in waiting_games:
        await message.reply("❗ برای این مبلغ یک بازی در انتظار است")
        return

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ پیوستن", callback_data=f"join_{amount}"),
        InlineKeyboardButton("❌ لغو شرط", callback_data=f"cancel_{amount}")
    )

    creator_name = get_display_name(message.from_user)

    msg = await message.reply(
        f"🎮 بازی {amount} 💎 ساخته شد!\n\n"
        f"👤 سازنده: {creator_name}\n"
        f"🎁 جایزه کل: {amount * 2} سکه\n\n"
        f"منتظر بازیکن دوم...",
        reply_markup=keyboard
    )

    waiting_games[amount] = {
        "creator": message.from_user.id,
        "creator_name": creator_name
    }

# ================== مدیریت دکمه‌های بازی ==================

@dp.callback_query_handler(lambda c: c.data.startswith(("join_", "cancel_")))
async def process_callback(callback: CallbackQuery):

    action, amount = callback.data.split("_")
    amount = int(amount)

    if amount not in waiting_games:
        await callback.answer("این بازی دیگر وجود ندارد", show_alert=True)
        return

    game_data = waiting_games[amount]
    creator_id = game_data["creator"]
    creator_name = game_data["creator_name"]

    user_id = callback.from_user.id
    user_name = get_display_name(callback.from_user)

    # ---------- لغو ----------
    if action == "cancel":

        if user_id != creator_id:
            await callback.answer("فقط سازنده می‌تواند لغو کند", show_alert=True)
            return

        del waiting_games[amount]
        await callback.message.edit_text("❌ بازی لغو شد")
        await callback.answer()
        return

    # ---------- پیوستن ----------
    if action == "join":

        if user_id == creator_id:
            await callback.answer("❗ نمی‌توانی به بازی خودت بپیوندی", show_alert=True)
            return

        get_user(user_id)
        balance = get_balance(user_id)

        if balance < amount:
            await callback.answer("❌ موجودی کافی نیست", show_alert=True)
            return

        prize = amount * 2

        winner_id = random.choice([creator_id, user_id])
        loser_id = creator_id if winner_id == user_id else user_id

        winner_name = creator_name if winner_id == creator_id else user_name
        loser_name = creator_name if loser_id == creator_id else user_name

        # کم کردن مبلغ از هر دو
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, creator_id))
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, user_id))

        # دادن جایزه به برنده
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (prize, winner_id))
        conn.commit()

        new_balance = get_balance(winner_id)

        del waiting_games[amount]

        await callback.message.edit_text(
            f"🎲 بازی انجام شد!\n\n"
            f"💰 مبلغ هر نفر: {amount} سکه\n"
            f"🎁 جایزه کل: {prize} سکه\n\n"
            f"🏆 برنده: {winner_name}\n"
            f"💎 موجودی جدید برنده: {new_balance} سکه\n\n"
            f"💀 بازنده: {loser_name}"
        )

        await callback.answer("بازی انجام شد!")

# ================== وب سرور Render ==================

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_web():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

# ================== اجرا ==================

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    executor.start_polling(dp, skip_updates=True)
