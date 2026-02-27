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

def get_display_name(user: types.User):
    if user.username:
        return f"@{user.username}"
    return user.full_name

# ================== کیبورد پیوی ==================
def main_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("💰 موجودی من"))
    return keyboard

# ================== حافظه بازی شرطی ==================
waiting_games = {}

# ================== START ==================
@dp.message_handler(commands=['start'], chat_type=types.ChatType.PRIVATE)
async def start(message: types.Message):
    get_user(message.from_user.id)
    await message.answer("🎮 به ربات خوش آمدی!", reply_markup=main_keyboard())

# ================== موجودی پیوی ==================
@dp.message_handler(lambda message: message.text == "💰 موجودی من", chat_type=types.ChatType.PRIVATE)
async def balance_private(message: types.Message):
    get_user(message.from_user.id)
    balance = get_balance(message.from_user.id)
    await message.answer(f"💰 موجودی شما: {balance} سکه 💎")

# ================== موجودی گروه ==================
@dp.message_handler(lambda message: message.text == "موجودی")
async def balance_group(message: types.Message):
    get_user(message.from_user.id)
    balance = get_balance(message.from_user.id)
    name = get_display_name(message.from_user)
    await message.reply(f"💰 موجودی {name}: {balance} سکه 💎")

# ================== انتقال سکه ==================
@dp.message_handler(lambda message: message.text and message.text.startswith("انتقال"))
async def transfer_coin(message: types.Message):
    try:
        parts = message.text.split()
        amount = int(parts[1])
        target_id = int(parts[2])
    except:
        await message.reply("فرمت صحیح:\nانتقال 50 123456789")
        return

    get_user(message.from_user.id)
    get_user(target_id)

    if get_balance(message.from_user.id) < amount:
        await message.reply("❌ موجودی کافی نیست")
        return

    add_balance(message.from_user.id, -amount)
    add_balance(target_id, amount)

    await message.reply(f"✅ {amount} سکه به آیدی {target_id} منتقل شد!")

# ================== بازی شرطی (بازی 50) ==================
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

    get_user(message.from_user.id)
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
    creator_name = get_display_name(message.from_user)

    await message.reply(f"🎮 بازی {amount} سکه\n👤 سازنده: {creator_name}\n🎁 جایزه کل: {amount*2} سکه\nمنتظر بازیکن دوم...", reply_markup=keyboard)
    waiting_games[amount] = {"creator": message.from_user.id, "creator_name": creator_name}

@dp.callback_query_handler(lambda c: c.data.startswith(("join_", "cancel_")))
async def handle_betting(callback: CallbackQuery):
    action, amount = callback.data.split("_")
    amount = int(amount)
    if amount not in waiting_games:
        await callback.answer("این بازی وجود ندارد", show_alert=True)
        return

    game_data = waiting_games[amount]
    creator_id = game_data["creator"]
    creator_name = game_data["creator_name"]

    user_id = callback.from_user.id
    user_name = get_display_name(callback.from_user)

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
        get_user(user_id)
        if get_balance(user_id) < amount:
            await callback.answer("موجودی کافی نیست", show_alert=True)
            return
        prize = amount*2
        winner_id = random.choice([creator_id, user_id])
        loser_id = creator_id if winner_id == user_id else user_id
        winner_name = creator_name if winner_id == creator_id else user_name
        loser_name = creator_name if loser_id == creator_id else user_name

        # کم کردن شرط
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, creator_id))
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, user_id))
        # جایزه
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (prize, winner_id))
        conn.commit()
        new_balance = get_balance(winner_id)
        del waiting_games[amount]

        await callback.message.edit_text(f"🎲 بازی انجام شد!\n🏆 برنده: {winner_name}\n💀 بازنده: {loser_name}\n🎁 جایزه: {prize}\n💎 موجودی جدید برنده: {new_balance}")
        await callback.answer("بازی انجام شد!")

# ================== سنگچی با شرط ==================
@dp.message_handler(lambda message: message.text and message.text.startswith("سنگچی"))
async def rock_paper_scissors(message: types.Message):
    try:
        parts = message.text.split()
        stake = int(parts[1]) if len(parts) > 1 else 0
    except:
        stake = 0

    get_user(message.from_user.id)
    balance = get_balance(message.from_user.id)

    if stake > 0 and balance < stake:
        await message.reply("❌ موجودی کافی برای شرط ندارید")
        return

    keyboard = InlineKeyboardMarkup(row_width=3)
    keyboard.add(
        InlineKeyboardButton("🪨 سنگ", callback_data=f"rps_rock_{stake}"),
        InlineKeyboardButton("📄 کاغذ", callback_data=f"rps_paper_{stake}"),
        InlineKeyboardButton("✂ قیچی", callback_data=f"rps_scissors_{stake}")
    )
    await message.reply("🎮 سنگ کاغذ قیچی\nیکی را انتخاب کن 👇", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("rps_"))
async def rps_result(callback: CallbackQuery):
    _, user_choice, stake_str = callback.data.split("_")
    stake = int(stake_str)

    bot_choice = random.choice(["rock", "paper", "scissors"])
    result = ""
    reward = 0

    if user_choice == bot_choice:
        result = "🤝 مساوی!"
    elif ((user_choice=="rock" and bot_choice=="scissors") or
          (user_choice=="scissors" and bot_choice=="paper") or
          (user_choice=="paper" and bot_choice=="rock")):
        result = "🏆 بردی!"
        reward = stake if stake>0 else 10
        add_balance(callback.from_user.id, reward)
    else:
        result = "😢 باختی!"
        # اگر شرط بود موجودی کم شود
        if stake>0:
            add_balance(callback.from_user.id, -stake)

    balance = get_balance(callback.from_user.id)
    emoji = {"rock":"🪨 سنگ","paper":"📄 کاغذ","scissors":"✂ قیچی"}
    await callback.message.edit_text(
        f"👤 انتخاب شما: {emoji[user_choice]}\n"
        f"🤖 انتخاب ربات: {emoji[bot_choice]}\n\n"
        f"{result}\n"
        f"🎁 جایزه: {reward}\n"
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

# ================== اجرا ==================
if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    executor.start_polling(dp, skip_updates=True)
