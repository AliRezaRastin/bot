import random
import sqlite3
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
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

def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
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

# ================== BETTING GAME (GROUP) ==================
waiting_games = {}

@dp.message_handler(lambda m: m.text and m.text.startswith("بازی"))
async def betting_game(message: types.Message):
    if message.chat.type == "private":
        return

    try:
        amount = int(message.text.split()[1])
    except:
        await message.reply("فرمت صحیح:\nبازی 50")
        return

    if amount <= 0:
        await message.reply("❌ مبلغ نامعتبر است")
        return

    get_user(message.from_user.id)

    if get_balance(message.from_user.id) < amount:
        await message.reply("❌ موجودی کافی نیست")
        return

    if amount in waiting_games:
        await message.reply("❗ یک بازی با این مبلغ فعال است")
        return

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ پیوستن", callback_data=f"join_{amount}"),
        InlineKeyboardButton("❌ لغو", callback_data=f"cancel_{amount}")
    )

    waiting_games[amount] = message.from_user.id
    name = get_name(message.from_user)

    await message.reply(
        f"🎮 بازی {amount} سکه\n"
        f"👤 سازنده: {name}\n"
        f"🎁 جایزه: {amount*2}\n"
        f"منتظر بازیکن دوم...",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data.startswith(("join_", "cancel_")))
async def handle_bet(callback: CallbackQuery):
    action, amount = callback.data.split("_")
    amount = int(amount)

    if amount not in waiting_games:
        await callback.answer("بازی یافت نشد", show_alert=True)
        return

    creator_id = waiting_games[amount]
    user_id = callback.from_user.id

    if action == "cancel":
        if user_id != creator_id:
            await callback.answer("فقط سازنده می‌تواند لغو کند", show_alert=True)
            return
        del waiting_games[amount]
        await callback.message.edit_text("❌ بازی لغو شد")
        await callback.answer()
        return

    if user_id == creator_id:
        await callback.answer("نمی‌توانی به بازی خودت بپیوندی", show_alert=True)
        return

    get_user(user_id)

    if get_balance(user_id) < amount:
        await callback.answer("موجودی کافی نیست", show_alert=True)
        return

    winner = random.choice([creator_id, user_id])
    loser = creator_id if winner == user_id else user_id

    add_balance(winner, amount)
    add_balance(loser, -amount)

    del waiting_games[amount]

    await callback.message.edit_text(
        f"🎲 بازی انجام شد!\n"
        f"🏆 برنده: {winner}\n"
        f"💀 بازنده: {loser}"
    )
    await callback.answer("بازی انجام شد!")

# ================== ROCK PAPER SCISSORS ==================
@dp.message_handler(lambda m: m.text and m.text.startswith("سنگچی"))
async def rps(message: types.Message):
    try:
        stake = int(message.text.split()[1])
    except:
        stake = 0

    get_user(message.from_user.id)

    if stake > 0 and get_balance(message.from_user.id) < stake:
        await message.reply("❌ موجودی کافی نیست")
        return

    keyboard = InlineKeyboardMarkup(row_width=3)
    keyboard.add(
        InlineKeyboardButton("🪨", callback_data=f"rps_rock_{stake}"),
        InlineKeyboardButton("📄", callback_data=f"rps_paper_{stake}"),
        InlineKeyboardButton("✂", callback_data=f"rps_scissors_{stake}")
    )

    await message.reply("انتخاب کن 👇", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("rps_"))
async def rps_result(callback: CallbackQuery):
    _, choice, stake = callback.data.split("_")
    stake = int(stake)

    bot_choice = random.choice(["rock", "paper", "scissors"])

    win = (
        (choice=="rock" and bot_choice=="scissors") or
        (choice=="paper" and bot_choice=="rock") or
        (choice=="scissors" and bot_choice=="paper")
    )

    result = ""
    if choice == bot_choice:
        result = "🤝 مساوی"
    elif win:
        result = "🏆 بردی!"
        add_balance(callback.from_user.id, stake if stake>0 else 10)
    else:
        result = "😢 باختی!"
        if stake>0:
            add_balance(callback.from_user.id, -stake)

    balance = get_balance(callback.from_user.id)

    await callback.message.edit_text(
        f"انتخاب شما: {choice}\n"
        f"انتخاب ربات: {bot_choice}\n\n"
        f"{result}\n"
        f"💎 موجودی: {balance}"
    )
    await callback.answer()

# ================== WEB SERVER FOR RENDER ==================
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
