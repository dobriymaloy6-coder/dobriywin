import logging
import os
import random
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiocryptopay import AioCryptoPay, Networks
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

# --- НАСТРОЙКИ (ВВЕДИТЕ ВАШИ ТОКЕНЫ ЗДЕСЬ) ---
TOKEN = "8814841234:AAFgf-HSoq0Q8YgZOLIFgIk43hclmMdjjnc"  # Токен от @BotFather
CRYPTO_BOT_TOKEN = "639499:AANlVeyFTk4dJ7z5PJvXfPXpITIfR9VVAOf"  # Токен от @CryptoBot

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

# Инициализация CryptoBot (MAIN_NET - для реальных денег, менять на TEST_NET для тестов)
def get_cryptopay():
    return AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.MAIN_NET)

# --- АВТОМАТИЧЕСКАЯ УСТАНОВКА ВЕБХУКА ПРИ СТАРТЕ ---
@app.on_event("startup")
async def on_startup():
    webhook_url = "https://dobriywin.onrender.com/api/telegram_webhook"
    await bot.set_webhook(webhook_url)
    logging.info(f"Webhook set to: {webhook_url}")

# --- БАЗА ДАННЫХ SQLite ---
def init_db():
    conn = sqlite3.connect("database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0,
            total_dep REAL DEFAULT 0.0,
            total_win REAL DEFAULT 0.0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            invoice_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            amount REAL,
            status TEXT DEFAULT 'active'
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_user_data(user_id: int):
    conn = sqlite3.connect("database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT balance, total_dep, total_win FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (user_id, balance, total_dep, total_win) VALUES (?, 0.0, 0.0, 0.0)", (user_id,))
        conn.commit()
        row = (0.0, 0.0, 0.0)
    conn.close()
    return {"balance": row[0], "total_dep": row[1], "total_win": row[2]}

def update_user_balance(user_id: int, amount: float, is_dep: bool = False):
    conn = sqlite3.connect("database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT balance, total_dep, total_win FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        cursor.execute("INSERT INTO users (user_id, balance, total_dep, total_win) VALUES (?, ?, ?, ?)", 
                       (user_id, max(0.0, amount), amount if is_dep else 0.0, 0.0))
    else:
        bal, dep, win = row
        new_balance = max(0.0, bal + amount)
        new_dep = dep + amount if (is_dep and amount > 0) else dep
        new_win = win + amount if (amount > 0 and not is_dep) else win
        cursor.execute("UPDATE users SET balance = ?, total_dep = ?, total_win = ? WHERE user_id = ?", 
                       (new_balance, new_dep, new_win, user_id))
    conn.commit()
    conn.close()


# --- TELEGRAM БОТ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user = get_user_data(user_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Открыть DobriyWin (Мини-приложение)", web_app=WebAppInfo(url="https://dobriymaloy6-coder.github.io/dobriywin/"))],
        [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="topup"),
         InlineKeyboardButton(text="📤 Вывести средства", callback_data="withdraw")],
        [InlineKeyboardButton(text="🔄 Обновить баланс", callback_data="refresh")]
    ])
    
    await message.answer(
        f"👋 Добро пожаловать в **DobriyWin**!\n\n"
        f"💰 Ваш текущий баланс: **{user['balance']:.2f} USDT**\n\n"
        f"Выбирайте игры в мини-приложении и побеждайте!",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "refresh")
async def cb_refresh(callback: types.CallbackQuery):
    user = get_user_data(callback.from_user.id)
    await callback.message.edit_text(
        f"👋 Добро пожаловать в **DobriyWin**!\n\n"
        f"💰 Ваш текущий баланс: **{user['balance']:.2f} USDT**\n\n"
        f"Выбирайте игры в мини-приложении и побеждайте!",
        reply_markup=callback.message.reply_markup,
        parse_mode="Markdown"
    )
    await callback.answer("Баланс обновлен!")

@dp.callback_query(F.data == "topup")
async def cb_topup(callback: types.CallbackQuery):
    try:
        cryptopay = get_cryptopay()
        amount_to_pay = 5.0  # Сумма пополнения по умолчанию в USDT
        
        invoice = await cryptopay.create_invoice(
            asset='USDT', 
            amount=amount_to_pay, 
            description="Пополнение баланса DobriyWin",
            paid_btn_name='callback',
            paid_btn_url='https://t.me/DobriyWin_Bot'
        )
        
        conn = sqlite3.connect("database.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO invoices (invoice_id, user_id, amount, status) VALUES (?, ?, ?, ?)", 
                       (invoice.invoice_id, callback.from_user.id, amount_to_pay, 'active'))
        conn.commit()
        conn.close()

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💳 Оплатить {amount_to_pay} USDT", url=invoice.bot_invoice_url)]
        ])
        await callback.message.answer(
            "💳 Счет создан через CryptoBot. Нажмите кнопку ниже для оплаты. Баланс пополнится **мгновенно** после подтверждения:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(e)
        await callback.message.answer("❌ Ошибка создания счета. Проверьте настройки CryptoBot.")
    await callback.answer()

@dp.callback_query(F.data == "withdraw")
async def cb_withdraw(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = get_user_data(user_id)
    if user['balance'] <= 0:
        await callback.message.answer("❌ У вас недостаточно средств для вывода.")
    else:
        withdrawing_amount = user['balance']
        update_user_balance(user_id, -withdrawing_amount, is_dep=False)
        
        try:
            cryptopay = get_cryptopay()
            transfer = await cryptopay.transfer_aiocryptopay(
                user_id=user_id,
                asset='USDT',
                amount=withdrawing_amount,
                spend_id=f"withdraw_{user_id}_{random.randint(1000,9999)}"
            )
            await callback.message.answer(
                f"📤 Успешно! Выведено **{withdrawing_amount:.2f} USDT** на ваш аккаунт CryptoBot.",
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(e)
            update_user_balance(user_id, withdrawing_amount, is_dep=False)
            await callback.message.answer("❌ Ошибка автоматического вывода. Убедитесь, что у вас есть чат с @CryptoBot.")
    await callback.answer()


# --- ВЕБХУКИ ДЛЯ TELEGRAM И CRYPTOBOT ---
@app.post("/api/telegram_webhook")
async def telegram_webhook(request: Request):
    json_data = await request.json()
    update = types.Update(**json_data)
    await dp.feed_update(bot, update)
    return JSONResponse({"status": "ok"})

@app.post("/api/cryptobot_webhook")
async def cryptobot_webhook(request: Request):
    data = await request.json()
    if data.get("update_type") == "invoice_paid":
        payload = data.get("payload", {})
        invoice_id = payload.get("invoice_id")
        
        conn = sqlite3.connect("database.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, amount, status FROM invoices WHERE invoice_id = ?", (invoice_id,))
        row = cursor.fetchone()
        
        if row and row[2] == 'active':
            user_id, amount, _ = row
            update_user_balance(user_id, amount, is_dep=True)
            cursor.execute("UPDATE invoices SET status = 'paid' WHERE invoice_id = ?", (invoice_id,))
            conn.commit()
            
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Оплата прошла успешно! Ваш баланс пополнен на **{amount:.2f} USDT**.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logging.error(e)
        conn.close()
    return JSONResponse({"status": "ok"})


# --- API Эндпоинты для игр (Математика 80/20) ---
@app.post("/api/get_balance")
async def api_get_balance(request: Request):
    data = await request.json()
    user = get_user_data(data.get("user_id", 0))
    return JSONResponse({"success": True, "balance": user['balance']})

@app.post("/api/game/coinflip")
async def api_coinflip(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    bet = float(data.get("bet", 0))
    choice = data.get("choice")
    
    user = get_user_data(user_id)
    if user['balance'] < bet:
        return JSONResponse({"success": False, "error": "Недостаточно средств"})

    update_user_balance(user_id, -bet)
    is_win = random.random() < 0.2
    
    if is_win:
        result_side = choice
        win_amount = bet * 1.95
        update_user_balance(user_id, win_amount)
    else:
        result_side = 'tails' if choice == 'heads' else 'heads'
        win_amount = 0.0

    new_user = get_user_data(user_id)
    return JSONResponse({
        "success": True,
        "win": is_win,
        "result_side": result_side,
        "win_amount": win_amount,
        "balance": new_user['balance']
    })

@app.post("/api/game/upgrader")
async def api_upgrader(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    bet = float(data.get("bet", 0))
    requested_chance = float(data.get("chance", 50))
    
    user = get_user_data(user_id)
    if user['balance'] < bet:
        return JSONResponse({"success": False, "error": "Недостаточно средств"})

    update_user_balance(user_id, -bet)

    forced_chance = min(requested_chance, 20.0) 
    if bet > 5.0:
        forced_chance = min(forced_chance, 10.0)

    roll = random.uniform(0, 100)
    is_win = roll <= forced_chance

    if is_win:
        multiplier = 95.0 / forced_chance
        win_amount = bet * multiplier
        update_user_balance(user_id, win_amount)
    else:
        win_amount = 0.0

    new_user = get_user_data(user_id)
    return JSONResponse({
        "success": True,
        "win": is_win,
        "roll": round(roll, 2),
        "chance_used": forced_chance,
        "win_amount": win_amount,
        "balance": new_user['balance']
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("bot:app", host="0.0.0.0", port=port)
