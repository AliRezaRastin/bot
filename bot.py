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

# ذخیره نام کاربران برای نمایش
user_names = {}

def get_user(user: types.User):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user.id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user.id,))
        conn.commit()

    # ذخیره نام برای نمایش
    if user.username:
        user_names[user.id] = f"@{user.username}"
    else:
        user_names[user.id] = user.full_name

def get_balance(user_id):
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone()[0]

def add_balance(user_id, amount):
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    conn.commit()

def get_display_name_by_id(user_id):
    return user_names.get(user_id, f"کاربر {user_id}")

# ================== کیبورد پیوی ==================

def main_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("💰 موجودی من"))
    return keyboard

waiting_games = {}

# ================== START ==================

@dp.message_handler(commands=['start'], chat_type=types.ChatType.PRIVATE)
async def start(message: types.Message):
    get_user(message.from_user)
    await message.answer("🎮 به ربات خوش آمدی!", reply_markup=main_keyboard())

# ================== موجودی پیوی ==================

@dp.message_handler(lambda message: message.text == "💰 موجودی من", chat_type=types.ChatType.PRIVATE)
async def balance_private(message: types.Message):
    get_user(message.from_user)
    balance = get_balance(message.from_user.id)
    await message.answer(f"💰 موجودی شما: {balance} سکه 💎")

# ================== موجودی گروه ==================

@dp.message_handler(lambda message: message.text == "موجودی")
async def balance_group(message: types.Message):
    get_user(message.from_user)
    balance = get_balance(message.from_user.id)
    name = get_display_name_by_id(message.from_user.id)
    await message.reply(f"💰 موجودی {name}: {balance} سکه 💎")

# =====================================================
# 🎲 بازی شرطی
# =====================================================

@dp.message_handler(lambda message: message.text and message.text.startswith("بازی"))
async def betting_game(message: types.Message):

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

    get_user(message.from_user)
    balance = get_balance(message.from_user.id)

    if balance < amount:
        await message.reply("❌ موجودی کافی نیست")
        return

    if amount in waiting_games:
        await message.reply("❗ یک بازی با این مبلغ در انتظار است")
        return

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ پیوستن", callback_data=f"join_{amount}"),
        InlineKeyboardButton("❌ لغو شرط", callback_data=f"cancel_{amount}")
    )

    creator_name = get_display_name_by_id(message.from_user.id)

    await message.reply(
        f"🎮 بازی {amount} سکه\n"
        f"👤 سازنده: {creator_name}\n"
        f"🎁 جایزه کل: {amount * 2} سکه\n\n"
        f"منتظر بازیکن دوم...",
        reply_markup=keyboard
    )

    waiting_games[amount] = message.from_user.id

@dp.callback_query_handler(lambda c: c.data.startswith(("join_", "cancel_")))
async def handle_betting(callback: CallbackQuery):

    action, amount = callback.data.split("_")
    amount = int(amount)

    if amount not in waiting_games:
        await callback.answer("این بازی وجود ندارد", show_alert=True)
        return

    creator_id = waiting_games[amount]
    user_id = callback.from_user.id

    get_user(callback.from_user)

    if action == "cancel":
        if user_id != creator_id:
            await callback.answer("فقط سازنده می‌تواند لغو کند", show_alert=True)
            return

        del waiting_games[amount]
        await callback.message.edit_text("❌ بازی لغو شد")
        await callback.answer()
        return

    if action == "join":

        if user_id == creator_id:
            await callback.answer("نمی‌توانی به بازی خودت بپیوندی", show_alert=True)
            return

        if get_balance(user_id) < amount:
            await callback.answer("موجودی کافی نیست", show_alert=True)
            return

        prize = amount * 2

        winner_id = random.choice([creator_id, user_id])
        loser_id = creator_id if winner_id == user_id else user_id

        winner_name = get_display_name_by_id(winner_id)
        loser_name = get_display_name_by_id(loser_id)

        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, creator_id))
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, user_id))
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (prize, winner_id))
        conn.commit()

        new_balance = get_balance(winner_id)

        del waiting_games[amount]

        await callback.message.edit_text(
            f"🎲 بازی انجام شد!\n\n"
            f"🏆 برنده: {winner_name}\n"
            f"💀 بازنده: {loser_name}\n\n"
            f"🎁 جایزه: {prize} سکه\n"
            f"💎 موجودی جدید برنده: {new_balance}"
        )

        await callback.answer("بازی انجام شد!")

# =====================================================
# ✂️ سنگچی
# =====================================================

@dp.message_handler(lambda message: message.text == "سنگچی")
async def rock_paper_scissors(message: types.Message):

    get_user(message.from_user)

    keyboard = InlineKeyboardMarkup(row_width=3)
    keyboard.add(
        InlineKeyboardButton("🪨 سنگ", callback_data="rps_rock"),
        InlineKeyboardButton("📄 کاغذ", callback_data="rps_paper"),
        InlineKeyboardButton("✂ قیچی", callback_data="rps_scissors"),
    )

    await message.reply("🎮 سنگ کاغذ قیچی\nیکی را انتخاب کن 👇", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("rps_"))
async def rps_result(callback: CallbackQuery):

    get_user(callback.from_user)

    user_choice = callback.data.split("_")[1]
    bot_choice = random.choice(["rock", "paper", "scissors"])

    result = ""
    reward = 0

    if user_choice == bot_choice:
        result = "🤝 مساوی!"
    elif (
        (user_choice == "rock" and bot_choice == "scissors") or
        (user_choice == "scissors" and bot_choice == "paper") or
        (user_choice == "paper" and bot_choice == "rock")
    ):
        result = "🏆 بردی!"
        reward = 10
        add_balance(callback.from_user.id, reward)
    else:
        result = "😢 باختی!"

    balance = get_balance(callback.from_user.id)

    emoji = {
        "rock": "🪨 سنگ",
        "paper": "📄 کاغذ",
        "scissors": "✂ قیچی"
    }

    player_name = get_display_name_by_id(callback.from_user.id)

    await callback.message.edit_text(
        f"👤 بازیکن: {player_name}\n"
        f"👤 انتخاب شما: {emoji[user_choice]}\n"
        f"🤖 انتخاب ربات: {emoji[bot_choice]}\n\n"
        f"{result}\n"
        f"🎁 جایزه: {reward} سکه\n"
        f"💎 موجودی فعلی: {balance}"
    )

    await callback.answer()

# ================== وب سرور ==================

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_web():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    executor.start_polling(dp, skip_updates=True)
