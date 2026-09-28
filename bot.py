import os
import logging
import sqlite3
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, Update

TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN")
WEB_APP_URL = "https://dobriywin.onrender.com"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None
dp = Dispatcher()
app = FastAPI()

CRYPTO_API_URL = "https://pay.crypt.bot/api/"

# --- БАЗА ДАННЫХ ---
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

# --- ВЕБ-СЕРВЕР ---

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h3>Файл index.html не найден в корне проекта</h3>"

@app.get("/api/balance")
async def api_balance(user_id: int):
    bal = get_user_balance(user_id)
    return JSONResponse({"success": True, "balance": bal})

async def create_crypto_invoice_link(user_id: int, amount: float):
    if not CRYPTO_BOT_TOKEN:
        return None
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    payload = {
        "asset": "USDT",
        "amount": str(amount),
        "description": f"Пополнение баланса DobriyWin для ID: {user_id}",
        "payload": str(user_id)
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{CRYPTO_API_URL}createInvoice", json=payload, headers=headers)
        result = response.json()
        if result.get("ok"):
            return result["result"]["pay_url"]
    return None

# Исправленный вебхук для оплаты CryptoBot
@app.post("/api/cryptobot_webhook")
async def cryptobot_webhook(request: Request):
    try:
        data = await request.json()
        logging.info(f"Получен вебхук от CryptoBot: {data}")
        
        if data.get("update_type") == "invoice_paid":
            invoice = data.get("payload", {})
            custom_payload = invoice.get("payload")
            amount_paid = float(invoice.get("amount", 0))
            
            if custom_payload:
                user_id = int(custom_payload)
                update_user_balance(user_id, amount_paid)
                logging.info(f"УСПЕХ! Баланс юзера {user_id} пополнен на {amount_paid} USDT")
                
                try:
                    await bot.send_message(
                        user_id, 
                        f"✅ <b>Оплата получена!</b> Ваш баланс пополнен на <b>{amount_paid} USDT</b>.", 
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logging.error(f"Не удалось отправить сообщение юзеру: {e}")
                    
    except Exception as e:
        logging.error(f"Ошибка обработки вебхука: {e}")
        
    return JSONResponse({"status": "ok"})

# --- ТЕЛЕГРАМ БОТ (Логика) ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    bal = get_user_balance(user_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть в DobriyWin", web_app=WebAppInfo(url=WEB_APP_URL))],
        [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="top_up_menu"), InlineKeyboardButton(text="📤 Вывести средства", callback_data="withdraw_menu")],
        [InlineKeyboardButton(text="🔄 Обновить баланс", callback_data="refresh_balance")]
    ])
    await message.answer(
        f"👋 Добро пожаловать в **dobriywin**!\n\n"
        f"💰 Ваш текущий баланс: <b>{bal:.2f} USDT</b>\n\n"
        "Используйте кнопки ниже:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@dp.callback_query(lambda c: c.data == "refresh_balance")
async def process_refresh(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    bal = get_user_balance(user_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть в DobriyWin", web_app=WebAppInfo(url=WEB_APP_URL))],
        [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="top_up_menu"), InlineKeyboardButton(text="📤 Вывести средства", callback_data="withdraw_menu")],
        [InlineKeyboardButton(text="🔄 Обновить баланс", callback_data="refresh_balance")]
    ])
    try:
        await callback.message.edit_text(
            f"👋 Добро пожаловать в **dobriywin**!\n\n"
            f"💰 Ваш текущий баланс: <b>{bal:.2f} USDT</b>\n\n"
            "Используйте кнопки ниже:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception:
        pass
    await callback.answer("Баланс обновлен!")

@dp.callback_query(lambda c: c.data == "top_up_menu")
async def process_topup_menu(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ 1 USDT", callback_data="pay_1"), InlineKeyboardButton(text="➕ 5 USDT", callback_data="pay_5")],
        [InlineKeyboardButton(text="➕ 10 USDT", callback_data="pay_10"), InlineKeyboardButton(text="➕ 25 USDT", callback_data="pay_25")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_home")]
    ])
    await callback.message.edit_text("Выберите сумму пополнения через CryptoBot:", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "withdraw_menu")
async def process_withdraw_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    bal = get_user_balance(user_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Вывести весь баланс", callback_data="do_withdraw")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_home")]
    ])
    await callback.message.edit_text(f"📤 Меню вывода\n\nВаш баланс: <b>{bal:.2f} USDT</b>\nДля вывода всех средств нажмите кнопку ниже:", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "do_withdraw")
async def process_do_withdraw(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    bal = get_user_balance(user_id)
    
    if bal <= 0:
        await callback.answer("На балансе нет средств для вывода!", show_alert=True)
        return

    if not CRYPTO_BOT_TOKEN:
        await callback.answer("Ошибка конфигурации вывода", show_alert=True)
        return

    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    payload = {
        "user_id": user_id,
        "asset": "USDT",
        "amount": str(bal),
        "spend_id": f"withdraw_{user_id}_{os.urandom(4).hex()}"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(f"{CRYPTO_API_URL}transfer", json=payload, headers=headers)
        result = response.json()
         
        if result.get("ok"):
            update_user_balance(user_id, -bal)
            await callback.message.edit_text(f"✅ Успешно! Выведено <b>{bal:.2f} USDT</b> на ваш CryptoBot.", parse_mode="HTML")
        else:
            err_msg = result.get("error", {}).get("name", "Ошибка перевода")
            await callback.answer(f"Ошибка вывода: {err_msg}", show_alert=True)

@dp.callback_query(lambda c: c.data == "back_home")
async def process_back(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    bal = get_user_balance(user_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть в DobriyWin", web_app=WebAppInfo(url=WEB_APP_URL))],
        [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="top_up_menu"), InlineKeyboardButton(text="📤 Вывести средства", callback_data="withdraw_menu")],
        [InlineKeyboardButton(text="🔄 Обновить баланс", callback_data="refresh_balance")]
    ])
    await callback.message.edit_text(
        f"👋 Главное меню:\n\n💰 Баланс: <b>{bal:.2f} USDT</b>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
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

@app.post("/api/telegram_webhook")
async def telegram_webhook(request: Request):
    json_data = await request.json()
    update = Update.model_validate(json_data, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"status": "ok"}

@app.on_event("startup")
async def on_startup():
    if bot:
        webhook_url = f"{WEB_APP_URL}/api/telegram_webhook"
        await bot.set_webhook(webhook_url)
        logging.info(f"Telegram Webhook установлен на: {webhook_url}")
