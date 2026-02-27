import random
import sqlite3
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils import executor

# گرفتن توکن از Environment
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

# ================== حافظه بازی‌ها ==================

waiting_games = {}
# ساختار:
# {
#   amount: {
#       "creator": user_id,
#       "message_id": msg_id
#   }
# }

# ================== دستورات ==================

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    get_user(message.from_user.id)
    await message.reply("🎮 خوش آمدی به ربات علی!\nموجودی اولیه: 100 💎")

# ================== ساخت بازی ==================

@dp.message_handler(lambda message: message.text.startswith("بازی"))
async def game(message: types.Message):

    try:
        amount = int(message.text.split()[1])
    except:
        await message.reply("فرمت صحیح:\nبازی 50")
        return

    if amount <= 0:
        await message.reply("❌ مبلغ باید بیشتر از صفر باشد")
        return

    get_user(message.from_user.id)

    cursor.execute("SELECT balance FROM users WHERE user_id=?", (message.from_user.id,))
    balance = cursor.fetchone()[0]

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

    msg = await message.reply(
        f"🎮 بازی {amount} 💎 ساخته شد!\n\n"
        f"سازنده: {message.from_user.full_name}\n"
        f"منتظر بازیکن دوم...",
        reply_markup=keyboard
    )

    waiting_games[amount] = {
        "creator": message.from_user.id,
        "message_id": msg.message_id
    }

# ================== مدیریت دکمه‌ها ==================

@dp.callback_query_handler(lambda c: c.data.startswith(("join_", "cancel_")))
async def process_callback(callback: CallbackQuery):

    action, amount = callback.data.split("_")
    amount = int(amount)

    if amount not in waiting_games:
        await callback.answer("این بازی دیگر وجود ندارد", show_alert=True)
        return

    game_data = waiting_games[amount]
    creator = game_data["creator"]
    user_id = callback.from_user.id

    # ---------- لغو بازی ----------
    if action == "cancel":

        if user_id != creator:
            await callback.answer("فقط سازنده می‌تواند لغو کند", show_alert=True)
            return

        del waiting_games[amount]

        await callback.message.edit_text("❌ بازی لغو شد")
        await callback.answer()
        return

    # ---------- پیوستن ----------
    if action == "join":

        if user_id == creator:
            await callback.answer("❗ نمی‌توانی به بازی خودت بپیوندی", show_alert=True)
            return

        get_user(user_id)

        cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
        balance = cursor.fetchone()[0]

        if balance < amount:
            await callback.answer("❌ موجودی کافی نیست", show_alert=True)
            return

        # انتخاب برنده
        winner = random.choice([creator, user_id])
        loser = creator if winner == user_id else user_id

        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, winner))
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, loser))
        conn.commit()

        del waiting_games[amount]

        await callback.message.edit_text(
            f"🎲 بازی انجام شد!\n\n"
            f"💰 مبلغ شرط: {amount} سکه\n\n"
            f"🏆 برنده: {winner}\n"
            f"💀 بازنده: {loser}"
        )

        await callback.answer("بازی انجام شد!")

# ================== وب سرور برای Render ==================

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_web():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

# ================== اجرای همزمان ==================

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    executor.start_polling(dp, skip_updates=True)
