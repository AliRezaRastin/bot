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

# ================== FORCE JOIN ==================
REQUIRED_CHANNELS = [
    {"username": "slfvtn", "link": "https://t.me/slfvtn"},
    {"username": "mohamaj_y", "link": "https://t.me/moamaj_y"}
]

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ================== DATABASE ==================
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

# ثبت یا بروزرسانی کاربر
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
    row = cursor.fetchone()
    return row[0] if row else 0

def update_balance(user_id, amount):
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    conn.commit()

def get_username(user_id):
    cursor.execute("SELECT username FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else str(user_id)

def ensure_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, 100))
        conn.commit()

# ================== KEYBOARD ==================
def main_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("💰 موجودی من"))
    return keyboard

# ================== START ==================
@dp.message_handler(commands=['start'], chat_type=types.ChatType.PRIVATE)
async def start(message: types.Message):
    register_user(message.from_user)
    await message.answer("🎮 خوش آمدی!", reply_markup=main_keyboard())

# ================== BALANCE ==================
@dp.message_handler(lambda message: message.text == "💰 موجودی من", chat_type=types.ChatType.PRIVATE)
async def balance_private(message: types.Message):
    register_user(message.from_user)
    balance = get_balance(message.from_user.id)
    await message.answer(f"💰 موجودی شما: {balance} سکه")

@dp.message_handler(lambda message: message.text == "موجودی")
async def balance_group(message: types.Message):
    ensure_user(message.from_user.id)
    balance = get_balance(message.from_user.id)
    username = get_username(message.from_user.id)
    await message.reply(f"💰 موجودی {username}: {balance} سکه")

# ================== BETTING GAME ==================
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

    ensure_user(message.from_user.id)
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
    ensure_user(joiner_id)

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

# ================== ROCK PAPER SCISSORS ==================
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

    ensure_user(message.from_user.id)
    balance = get_balance(message.from_user.id)
    if balance < stake:
        await message.reply("موجودی کافی نیست")
        return

    keyboard = InlineKeyboardMarkup(row_width=3)
    keyboard.add(
        InlineKeyboardButton("🪨 سنگ", callback_data=f"rps|rock|{stake}|{message.from_user.id}"),
        InlineKeyboardButton("📄 کاغذ", callback_data=f"rps|paper|{stake}|{message.from_user.id}"),
        InlineKeyboardButton("✂ قیچی", callback_data=f"rps|scissors|{stake}|{message.from_user.id}")
    )

    await message.reply(
        f"🎮 بازی سنگچی با شرط {stake} سکه\nفقط سازنده می‌تواند انتخاب کند 👇",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data.startswith("rps|"))
async def rps_result(callback: CallbackQuery):
    _, user_choice, stake, owner_id = callback.data.split("|")
    stake = int(stake)
    owner_id = int(owner_id)

    if callback.from_user.id != owner_id:
        await callback.answer("این بازی برای شما نیست ❌", show_alert=True)
        return

    ensure_user(owner_id)
    balance = get_balance(owner_id)
    if balance < stake:
        await callback.answer("موجودی کافی نیست ❌", show_alert=True)
        return

    bot_choice = random.choice(["rock", "paper", "scissors"])
    if user_choice == bot_choice:
        result_text = "🤝 مساوی!"
        change = 0
    elif (user_choice=="rock" and bot_choice=="scissors") or \
         (user_choice=="scissors" and bot_choice=="paper") or \
         (user_choice=="paper" and bot_choice=="rock"):
        result_text = "🏆 بردی!"
        change = stake
        update_balance(owner_id, stake)
    else:
        result_text = "😢 باختی!"
        change = -stake
        update_balance(owner_id, -stake)

    new_balance = get_balance(owner_id)
    username = get_username(owner_id)
    emoji = {"rock":"🪨 سنگ","paper":"📄 کاغذ","scissors":"✂ قیچی"}

    await callback.message.edit_text(
        f"👤 بازیکن: {username}\n\n"
        f"انتخاب شما: {emoji[user_choice]}\n"
        f"انتخاب ربات: {emoji[bot_choice]}\n\n"
        f"{result_text}\n"
        f"تغییر موجودی: {change}\n"
        f"موجودی فعلی: {new_balance}"
    )
    await callback.answer()

# ================== TRANSFER ==================
@dp.message_handler(lambda message: message.text and message.text.startswith("انتقال"))
async def transfer_coins(message: types.Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("فرمت صحیح:\nانتقال 50\nیا\nانتقال 50 @username")
        return
    try:
        amount = int(parts[1])
    except:
        await message.reply("عدد سکه نامعتبر است")
        return
    if amount <= 0:
        await message.reply("مبلغ باید بیشتر از صفر باشد")
        return

    sender = message.from_user
    ensure_user(sender.id)
    if get_balance(sender.id) < amount:
        await message.reply("موجودی کافی نیست ❌")
        return

    receiver_id = None
    receiver_name = None

    if message.reply_to_message:
        receiver = message.reply_to_message.from_user
        ensure_user(receiver.id)
        if receiver.id == sender.id:
            await message.reply("نمی‌توانی به خودت انتقال بدهی ❌")
            return
        receiver_id = receiver.id
        receiver_name = get_username(receiver_id)
    elif len(parts) >= 3:
        username = parts[2]
        if not username.startswith("@"):
            await message.reply("نام کاربری باید با @ باشد")
            return
        cursor.execute("SELECT user_id FROM users WHERE username=?", (username,))
        data = cursor.fetchone()
        if not data:
            await message.reply("کاربر پیدا نشد ❌")
            return
        receiver_id = data[0]
        receiver_name = username
        if receiver_id == sender.id:
            await message.reply("نمی‌توانی به خودت انتقال بدهی ❌")
            return
    else:
        await message.reply("کاربر مقصد مشخص نیست")
        return

    update_balance(sender.id, -amount)
    update_balance(receiver_id, amount)
    new_sender_balance = get_balance(sender.id)
    sender_name = get_username(sender.id)

    await message.reply(
        f"✅ انتقال انجام شد\nاز: {sender_name}\nبه: {receiver_name}\nمبلغ: {amount} سکه\nموجودی جدید شما: {new_sender_balance}"
    )

# ================== FORCE JOIN ==================
@dp.message_handler(lambda message: message.chat.type in ["group","supergroup"], content_types=types.ContentTypes.ANY)
async def force_join_check(message: types.Message):
    user_id = message.from_user.id
    not_joined = []

    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(f"@{channel['username']}", user_id)
            if member.status in ["left","kicked"]:
                not_joined.append(channel)
        except Exception as e:
            print(f"Error checking join: {e}")

    if not_joined:
        try:
            await message.delete()
        except:
            pass
        keyboard = InlineKeyboardMarkup(row_width=1)
        for channel in not_joined:
            keyboard.add(InlineKeyboardButton(f"📢 عضویت در {channel['username']}", url=channel["link"]))
        await message.answer("❌ برای ارسال پیام باید عضو کانال‌های زیر شوید 👇", reply_markup=keyboard)

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

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    executor.start_polling(dp, skip_updates=True)
