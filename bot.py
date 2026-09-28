import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, Update
from aiocryptopay import AioCryptoPay, Networks
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

# --- НАСТРОЙКИ ---
TOKEN = "ВАШ_ТОКЕН_БОТА"  # Замените на токен от BotFather
CRYPTO_BOT_TOKEN = "ВАШ_ТОКЕН_CRYPTO_BOT"  # Замените на токен от CryptoBot

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()
cryptopay = AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.TEST_NET)

# --- БАЗА ДАННЫХ SQLite ---
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_user_balance(user_id: int) -> float:
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    else:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0.0)", (user_id,))
        conn.commit()
        conn.close()
        return 0.0

def update_user_balance(user_id: int, amount: float):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, max(0.0, amount)))
    else:
        new_balance = max(0.0, row[0] + amount)
        cursor.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
    conn.commit()
    conn.close()


# --- TELEGRAM БОТ ХЕНДЛЕРЫ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть в DobriyWin", web_app=WebAppInfo(url="https://dobriymaloy6-coder.github.io/dobriywin/"))],
        [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="topup"),
         InlineKeyboardButton(text="📤 Вывести средства", callback_data="withdraw")],
        [InlineKeyboardButton(text="🔄 Обновить баланс", callback_data="refresh")]
    ])
    
    await message.answer(
        f"👋 Добро пожаловать в **dobriywin**!\n\n"
        f"💰 Ваш текущий баланс: **{balance:.2f} USDT**\n\n"
        f"Используйте кнопки ниже:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "refresh")
async def cb_refresh(callback: types.CallbackQuery):
    balance = get_user_balance(callback.from_user.id)
    await callback.message.edit_text(
        f"👋 Добро пожаловать в **dobriywin**!\n\n"
        f"💰 Ваш текущий баланс: **{balance:.2f} USDT**\n\n"
        f"Используйте кнопки ниже:",
        reply_markup=callback.message.reply_markup,
        parse_mode="Markdown"
    )
    await callback.answer("Баланс обновлен!")

@dp.callback_query(F.data == "topup")
async def cb_topup(callback: types.CallbackQuery):
    try:
        invoice = await cryptopay.create_invoice(asset='USDT', amount=1.0, description="Пополнение баланса DobriyWin")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить 1 USDT", url=invoice.bot_invoice_url)]
        ])
        await callback.message.answer(
            "💳 Счет на пополнение создан через CryptoBot. Нажмите кнопку ниже для оплаты:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception:
        await callback.message.answer("❌ Ошибка создания счета. Проверьте токен CryptoBot.")
    await callback.answer()

@dp.callback_query(F.data == "withdraw")
async def cb_withdraw(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    balance = get_user_balance(user_id)
    if balance <= 0:
        await callback.message.answer("❌ У вас недостаточно средств для вывода.")
    else:
        update_user_balance(user_id, -balance)
        await callback.message.answer(
            f"📤 Успешно создана заявка на вывод **{balance:.2f} USDT**. Средства отправлены.",
            parse_mode="Markdown"
        )
    await callback.answer()


# --- FASTAPI ЭНДПОИНТЫ ---
@app.post("/api/telegram_webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"status": "ok"}

@app.post("/api/get_balance")
async def api_get_balance(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    if not user_id:
        return JSONResponse({"success": False, "error": "No user_id provided"})
    balance = get_user_balance(user_id)
    return JSONResponse({"success": True, "balance": balance})

@app.post("/api/update_balance")
async def api_update_balance(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    amount = data.get("amount")
    
    if not user_id or amount is None:
        return JSONResponse({"success": False, "error": "Invalid data"})
    
    update_user_balance(user_id, float(amount))
    new_balance = get_user_balance(user_id)
    return JSONResponse({"success": True, "balance": new_balance})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("bot:app", host="0.0.0.0", port=port)
