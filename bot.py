import random
import sqlite3
import os
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

TOKEN = os.getenv("8617861447:AAFIrVf6O7cuJxkd4-drQKnBhf1enGn66jo")

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

conn = sqlite3.connect("database.db")
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

waiting_games = {}

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    get_user(message.from_user.id)
    await message.reply("🎮 خوش آمدی به ربات علی!\nموجودی اولیه: 100 💎")

@dp.message_handler(lambda message: message.text.startswith("بازی"))
async def game(message: types.Message):
    try:
        amount = int(message.text.split()[1])
    except:
        await message.reply("فرمت صحیح: بازی 50")
        return

    get_user(message.from_user.id)

    cursor.execute("SELECT balance FROM users WHERE user_id=?", (message.from_user.id,))
    balance = cursor.fetchone()[0]

    if balance < amount:
        await message.reply("❌ موجودی کافی نیست")
        return

    if amount in waiting_games:
        player1 = waiting_games[amount]
        player2 = message.from_user.id

        winner = random.choice([player1, player2])
        loser = player1 if winner == player2 else player2

        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, winner))
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, loser))
        conn.commit()

        del waiting_games[amount]

        await message.reply(f"🎲 بازی انجام شد!\nبرنده: {winner}\nبازنده: {loser}")
    else:
        waiting_games[amount] = message.from_user.id
        await message.reply(f"⏳ بازی {amount} 💎 ساخته شد.\nمنتظر نفر دوم...")

if name == "main":
    executor.start_polling(dp, skip_updates=True)