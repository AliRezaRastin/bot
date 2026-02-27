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
    balance INTEGER DEFAULT 100,
    username TEXT
)
""")
conn.commit()

# ================== USER FUNCTIONS ==================
def get_user(user: types.User):
    cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,))
    data = cursor.fetchone()
    if data is None:
        cursor.execute(
            "INSERT INTO users (user_id, balance, username) VALUES (?, ?, ?)",
            (user.id, 100, user.username)
        )
    else:
        cursor.execute(
            "UPDATE users SET username=? WHERE user_id=?",
            (user.username, user.id)
        )
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
    get_user(message.from_user)

    text = (
        "🚀✨ به ربات خوش آمدید!\n\n"
        "💎 بازی کن و امتیاز بگیر\n\n"
        "👇 انتخاب کن:"
    )

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("💰 موجودی من", callback_data="balance"),
        InlineKeyboardButton("🎮 بازی شرطی", callback_data="bet_info"),
        InlineKeyboardButton("✂ سنگچی", callback_data="rps_info"),
        InlineKeyboardButton("👤 پروفایل", callback_data="profile")
    )

    await message.answer(text, reply_markup=keyboard)


# ================== CALLBACKS ==================
@dp.callback_query_handler(lambda c: c.data == "balance")
async def balance_callback(callback: CallbackQuery):
    get_user(callback.from_user)
    balance = get_balance(callback.from_user.id)
    await callback.answer()
    await callback.message.answer(f"موجودی شما:\n{balance}")

@dp.callback_query_handler(lambda c: c.data == "profile")
async def profile_callback(callback: CallbackQuery):
    get_user(callback.from_user)
    balance = get_balance(callback.from_user.id)
    await callback.answer()
    await callback.message.answer(
        f"نام: {get_name(callback.from_user)}\n"
        f"موجودی: {balance}"
    )

@dp.callback_query_handler(lambda c: c.data == "bet_info")
async def bet_info(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("در گروه بنویس:\nبازی 50")

@dp.callback_query_handler(lambda c: c.data == "rps_info")
async def rps_info(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("بنویس:\nسنگچی 20")


# ================== موجودی گروه ==================
@dp.message_handler(lambda m: m.text == "موجودی")
async def balance_group(message: types.Message):
    get_user(message.from_user)
    balance = get_balance(message.from_user.id)
    await message.reply(f"موجودی شما:\n{balance}")


# ================== انتقال سکه حرفه‌ای ==================
@dp.message_handler(lambda m: m.text and m.text.startswith("انتقال"))
async def transfer_coin(message: types.Message):
    parts = message.text.split()

    if len(parts) < 2:
        await message.reply("فرمت:\nانتقال 50 @username\nیا ریپلای کن")
        return

    try:
        amount = int(parts[1])
    except:
        await message.reply("عدد نامعتبر است")
        return

    sender = message.from_user
    get_user(sender)

    target_id = None

    # حالت ریپلای
    if message.reply_to_message:
        target = message.reply_to_message.from_user
        target_id = target.id
        get_user(target)

    # حالت آیدی عددی
    elif len(parts) >= 3 and parts[2].isdigit():
        target_id = int(parts[2])
        cursor.execute("SELECT user_id FROM users WHERE user_id=?", (target_id,))
        if not cursor.fetchone():
            await message.reply("کاربر در ربات ثبت نشده")
            return

    # حالت یوزرنیم
    elif len(parts) >= 3 and parts[2].startswith("@"):
        username = parts[2][1:]
        cursor.execute("SELECT user_id FROM users WHERE username=?", (username,))
        data = cursor.fetchone()
        if not data:
            await message.reply("کاربر یافت نشد")
            return
        target_id = data[0]

    else:
        await message.reply("کاربر مقصد مشخص نیست")
        return

    if sender.id == target_id:
        await message.reply("نمی‌توانی به خودت انتقال دهی")
        return

    if get_balance(sender.id) < amount:
        await message.reply("موجودی کافی نیست")
        return

    add_balance(sender.id, -amount)
    add_balance(target_id, amount)

    await message.reply(f"{amount} امتیاز منتقل شد ✅")


# ================== بازی شرطی ==================
waiting_games = {}

@dp.message_handler(lambda m: m.text and m.text.startswith("بازی"))
async def betting_game(message: types.Message):
    if message.chat.type == "private":
        return

    try:
        amount = int(message.text.split()[1])
    except:
        await message.reply("مثال: بازی 50")
        return

    get_user(message.from_user)

    if get_balance(message.from_user.id) < amount:
        await message.reply("موجودی کافی نیست")
        return

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("پیوستن", callback_data=f"join_{amount}")
    )

    waiting_games[amount] = message.from_user
    await message.reply(
        f"بازی {amount} امتیاز\n"
        f"سازنده: {get_name(message.from_user)}",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data.startswith("join_"))
async def join_game(callback: CallbackQuery):
    amount = int(callback.data.split("_")[1])

    if amount not in waiting_games:
        await callback.answer("یافت نشد", show_alert=True)
        return

    creator = waiting_games[amount]
    player = callback.from_user

    if player.id == creator.id:
        await callback.answer("نمی‌شود", show_alert=True)
        return

    get_user(player)

    if get_balance(player.id) < amount:
        await callback.answer("موجودی کافی نیست", show_alert=True)
        return

    winner = random.choice([creator, player])
    loser = creator if winner.id != creator.id else player

    add_balance(winner.id, amount)
    add_balance(loser.id, -amount)

    del waiting_games[amount]

    await callback.message.edit_text(
        f"🏆 برنده: {get_name(winner)}\n"
        f"❌ بازنده: {get_name(loser)}\n"
        f"💰 مبلغ: {amount}"
    )
    await callback.answer()


# ================== سنگچی ==================
@dp.message_handler(lambda m: m.text and m.text.startswith("سنگچی"))
async def rps(message: types.Message):
    try:
        stake = int(message.text.split()[1])
    except:
        await message.reply("مثال: سنگچی 20")
        return

    get_user(message.from_user)

    if get_balance(message.from_user.id) < stake:
        await message.reply("موجودی کافی نیست")
        return

    keyboard = InlineKeyboardMarkup(row_width=3)
    keyboard.add(
        InlineKeyboardButton("🪨", callback_data=f"rps_rock_{stake}"),
        InlineKeyboardButton("📄", callback_data=f"rps_paper_{stake}"),
        InlineKeyboardButton("✂", callback_data=f"rps_scissors_{stake}")
    )

    await message.reply("انتخاب کن:", reply_markup=keyboard)

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

    if choice == bot_choice:
        result = "مساوی"
    elif win:
        result = "بردی 🎉"
        add_balance(callback.from_user.id, stake)
    else:
        result = "باختی ❌"
        add_balance(callback.from_user.id, -stake)

    balance = get_balance(callback.from_user.id)

    await callback.message.edit_text(
        f"تو: {choice}\n"
        f"ربات: {bot_choice}\n\n"
        f"{result}\n"
        f"موجودی: {balance}"
    )
    await callback.answer()


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
