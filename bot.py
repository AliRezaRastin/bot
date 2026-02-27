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
    username TEXT,
    balance INTEGER DEFAULT 100
)
""")
conn.commit()

def register_user(user: types.User):
    username = f"@{user.username}" if user.username else user.full_name

    cursor.execute("SELECT * FROM users WHERE user_id=?", (user.id,))
    data = cursor.fetchone()

    if not data:
        cursor.execute(
            "INSERT INTO users (user_id, username, balance) VALUES (?, ?, ?)",
            (user.id, username, 100)
        )
    else:
        cursor.execute(
            "UPDATE users SET username=? WHERE user_id=?",
            (username, user.id)
        )

    conn.commit()

def get_balance(user_id):
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone()[0]

def update_balance(user_id, amount):
    cursor.execute(
        "UPDATE users SET balance = balance + ? WHERE user_id=?",
        (amount, user_id)
    )
    conn.commit()

def get_username(user_id):
    cursor.execute("SELECT username FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else "کاربر"

# ================== کیبورد پیوی ==================

def main_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("💰 موجودی من"))
    return keyboard

# ================== START ==================

@dp.message_handler(commands=['start'], chat_type=types.ChatType.PRIVATE)
async def start(message: types.Message):
    register_user(message.from_user)
    await message.answer("🎮 خوش آمدی!", reply_markup=main_keyboard())

# ================== موجودی ==================

@dp.message_handler(lambda message: message.text == "💰 موجودی من", chat_type=types.ChatType.PRIVATE)
async def balance_private(message: types.Message):
    register_user(message.from_user)
    balance = get_balance(message.from_user.id)
    await message.answer(f"💰 موجودی شما: {balance} سکه")

@dp.message_handler(lambda message: message.text == "موجودی")
async def balance_group(message: types.Message):
    register_user(message.from_user)
    balance = get_balance(message.from_user.id)
    username = get_username(message.from_user.id)
    await message.reply(f"💰 موجودی {username}: {balance} سکه")

# =====================================================
# 🎲 بازی شرطی دو نفره
# =====================================================

waiting_games = {}

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
        await message.reply("مبلغ باید بیشتر از صفر باشد")
        return

    register_user(message.from_user)

    if get_balance(message.from_user.id) < amount:
        await message.reply("موجودی کافی نیست")
        return

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ پیوستن", callback_data=f"join_{amount}"),
        InlineKeyboardButton("❌ لغو", callback_data=f"cancel_{amount}")
    )

    waiting_games[amount] = message.from_user.id
    username = get_username(message.from_user.id)

    await message.reply(
        f"🎮 بازی {amount} سکه\n"
        f"سازنده: {username}\n"
        f"جایزه: {amount*2} سکه",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data.startswith(("join_", "cancel_")))
async def handle_game(callback: CallbackQuery):

    action, amount = callback.data.split("_")
    amount = int(amount)

    if amount not in waiting_games:
        await callback.answer("بازی وجود ندارد", show_alert=True)
        return

    creator_id = waiting_games[amount]
    joiner_id = callback.from_user.id

    register_user(callback.from_user)

    if action == "cancel":
        if joiner_id != creator_id:
            await callback.answer("فقط سازنده می‌تواند لغو کند", show_alert=True)
            return

        del waiting_games[amount]
        await callback.message.edit_text("❌ بازی لغو شد")
        return

    if action == "join":

        if joiner_id == creator_id:
            await callback.answer("نمی‌توانی به بازی خودت بپیوندی", show_alert=True)
            return

        if get_balance(joiner_id) < amount:
            await callback.answer("موجودی کافی نیست", show_alert=True)
            return

        update_balance(creator_id, -amount)
        update_balance(joiner_id, -amount)

        winner = random.choice([creator_id, joiner_id])
        loser = creator_id if winner == joiner_id else joiner_id

        prize = amount * 2
        update_balance(winner, prize)

        winner_name = get_username(winner)
        loser_name = get_username(loser)

        del waiting_games[amount]

        await callback.message.edit_text(
            f"🏆 برنده: {winner_name}\n"
            f"❌ بازنده: {loser_name}\n"
            f"🎁 جایزه: {prize} سکه"
        )

# =====================================================
# ✂️ سنگچی (فقط سازنده بتواند بازی کند)
# =====================================================

@dp.message_handler(lambda message: message.text and message.text.startswith("سنگچی"))
async def rps_game(message: types.Message):

    try:
        stake = int(message.text.split()[1])
    except:
        await message.reply("فرمت صحیح:\nسنگچی 20")
        return

    if stake <= 0:
        await message.reply("عدد شرط نامعتبر است")
        return

    register_user(message.from_user)

    if get_balance(message.from_user.id) < stake:
        await message.reply("موجودی کافی نیست")
        return

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("🪨 سنگ", callback_data=f"rps_rock_{stake}_{message.from_user.id}"),
        InlineKeyboardButton("📄 کاغذ", callback_data=f"rps_paper_{stake}_{message.from_user.id}"),
        InlineKeyboardButton("✂ قیچی", callback_data=f"rps_scissors_{stake}_{message.from_user.id}")
    )

    await message.reply("انتخاب کن:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("rps_"))
async def rps_result(callback: CallbackQuery):

    _, user_choice, stake, owner_id = callback.data.split("_")
    stake = int(stake)
    owner_id = int(owner_id)

    # فقط سازنده بازی اجازه دارد
    if callback.from_user.id != owner_id:
        await callback.answer("این بازی برای شما نیست ❌", show_alert=True)
        return

    user_id = callback.from_user.id
    register_user(callback.from_user)

    if get_balance(user_id) < stake:
        await callback.answer("موجودی کافی نیست", show_alert=True)
        return

    bot_choice = random.choice(["rock", "paper", "scissors"])

    win = (
        (user_choice == "rock" and bot_choice == "scissors") or
        (user_choice == "scissors" and bot_choice == "paper") or
        (user_choice == "paper" and bot_choice == "rock")
    )

    if user_choice == bot_choice:
        result = "مساوی"
        reward = 0
    elif win:
        result = "بردی 🎉"
        reward = stake
        update_balance(user_id, stake)
    else:
        result = "باختی 😢"
        reward = -stake
        update_balance(user_id, -stake)

    balance = get_balance(user_id)
    username = get_username(user_id)

    emoji = {"rock":"🪨","paper":"📄","scissors":"✂"}

    await callback.message.edit_text(
        f"بازیکن: {username}\n"
        f"انتخاب شما: {emoji[user_choice]}\n"
        f"انتخاب ربات: {emoji[bot_choice]}\n\n"
        f"نتیجه: {result}\n"
        f"تغییر موجودی: {reward}\n"
        f"موجودی فعلی: {balance}"
    )

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
