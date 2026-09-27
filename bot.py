import os
import logging
import sqlite3
import asyncio
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN")
WEB_APP_URL = "https://dobriywin.onrender.com"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None
dp = Dispatcher()
app = FastAPI()

CRYPTO_API_URL = "https://pay.crypt.bot/api/"

# --- РАБОТА С БАЗОЙ ДАННЫХ (SQLite) ---
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
    if not row:
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, 0.0))
        conn.commit()
        balance = 0.0
    else:
        balance = row[0]
    conn.close()
    return balance

def update_user_balance(user_id: int, amount: float):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, amount))
    else:
        new_balance = row[0] + amount
        cursor.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
    conn.commit()
    conn.close()

# --- ВЕБ-СЕРВЕР (FastAPI для игры и CryptoBot Webhook) ---

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h3>Файл index.html не найден в корне проекта</h3>"

# API для получения баланса игрока в игре
@app.get("/api/balance")
async def api_balance(user_id: int):
    bal = get_user_balance(user_id)
    return JSONResponse({"success": True, "balance": bal})

# Создание инвойса на пополнение из чата бота
async def create_crypto_invoice_link(user_id: int, amount: float):
    if not CRYPTO_BOT_TOKEN:
        return None
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    payload = {
        "asset": "USDT",
        "amount": str(amount),
        "description": f"Пополнение баланса DobriyWin для ID: {user_id}",
        "payload": str(user_id) # Зашиваем user_id прямо в платеж
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{CRYPTO_API_URL}createInvoice", json=payload, headers=headers)
        result = response.json()
        if result.get("ok"):
            return result["result"]["pay_url"]
    return None

# Вебхук, куда CryptoBot присылает уведомления об успешной оплате
@app.post("/api/cryptobot_webhook")
async def cryptobot_webhook(request: Request):
    data = await request.json()
    if data.get("update_type") == "invoice_paid":
        invoice = data.get("payload", {}).get("invoice", {})
        custom_payload = invoice.get("payload") # Здесь лежит наш user_id
        amount_paid = float(invoice.get("amount", 0))
        
        if custom_payload:
            user_id = int(custom_payload)
            update_user_balance(user_id, amount_paid)
            logging.info(f"Баланс юзера {user_id} пополнен на {amount_paid} USDT через CryptoBot")
            
            try:
                await bot.send_message(user_id, f"✅ Успешно! Ваш баланс пополнен на <b>{amount_paid} USDT</b>.", parse_mode="HTML")
            except Exception as e:
                logging.error(f"Не удалось отправить сообщение о пополнении: {e}")
                
    return JSONResponse({"status": "ok"})

# API вывода средств
@app.post("/api/withdraw")
async def withdraw(request: Request):
    if not CRYPTO_BOT_TOKEN:
        return JSONResponse({"success": False, "error": "CryptoBot token not configured"}, status_code=500)
        
    data = await request.json()
    amount = float(data.get("amount", 0))
    user_id = int(data.get("user_id", 0))
    
    if amount <= 0 or not user_id:
        return JSONResponse({"success": False, "error": "Неверные данные"})

    current_bal = get_user_balance(user_id)
    if current_bal < amount:
        return JSONResponse({"success": False, "error": "Недостаточно средств на балансе"})

    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    payload = {
        "user_id": user_id,
        "asset": "USDT",
        "amount": str(amount),
        "spend_id": f"withdraw_{user_id}_{os.urandom(4).hex()}"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(f"{CRYPTO_API_URL}transfer", json=payload, headers=headers)
        result = response.json()
         
        if result.get("ok"):
            update_user_balance(user_id, -amount)
            return JSONResponse({"success": True})
        else:
            err_msg = result.get("error", {}).get("name", "Ошибка перевода")
            return JSONResponse({"success": False, "error": err_msg})

# --- ТЕЛЕГРАМ БОТ (Команды и Кнопки) ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    get_user_balance(user_id) # Регистрация юзера с 0 балансом
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть в DobriyWin", web_app=WebAppInfo(url=WEB_APP_URL))],
        [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="top_up_menu")]
    ])
    await message.answer(
        "👋 Добро пожаловать в **dobriywin**!\n\n"
        "💎 Реальная игра на USDT.\n"
        "Используйте кнопки ниже для игры и пополнения счета:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query(lambda c: c.data == "top_up_menu")
async def process_topup_menu(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ 1 USDT", callback_data="pay_1"), InlineKeyboardButton(text="➕ 5 USDT", callback_data="pay_5")],
        [InlineKeyboardButton(text="➕ 10 USDT", callback_data="pay_10"), InlineKeyboardButton(text="➕ 25 USDT", callback_data="pay_25")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_home")]
    ])
    await callback.message.edit_text("Выберите сумму пополнения через CryptoBot:", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_home")
async def process_back(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть в DobriyWin", web_app=WebAppInfo(url=WEB_APP_URL))],
        [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="top_up_menu")]
    ])
    await callback.message.edit_text("Главное меню:", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("pay_"))
async def process_pay(callback: types.CallbackQuery):
    amount = float(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    pay_url = await create_crypto_invoice_link(user_id, amount)
    if pay_url:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить счет", url=pay_url)],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="top_up_menu")]
        ])
        await callback.message.edit_text(f"Счет на пополнение <b>{amount} USDT</b> создан.\nНажмите кнопку ниже для оплаты:", reply_markup=keyboard, parse_mode="HTML")
    else:
        await callback.answer("Ошибка создания счета в CryptoBot", show_alert=True)

@app.on_event("startup")
async def on_startup():
    if bot:
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            asyncio.create_task(dp.start_polling(bot))
            logging.info("Telegram bot polling started successfully!")
        except Exception as e:
            logging.error(f"Polling start error: {e}")
