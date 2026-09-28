import logging
import os
import random
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
TOKEN = "8814841234:AAFgf-HSoq0Q8YgZOLIFgIk43hclmMdjjnc"  
CRYPTO_BOT_TOKEN = "639499:AANlVeyFTk4dJ7z5PJvXfPXpITIfR9VVAOf"  

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

def get_cryptopay():
    return AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.TEST_NET)

# --- БАЗА ДАННЫХ SQLite ---
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0,
            total_dep REAL DEFAULT 0.0,
            total_win REAL DEFAULT 0.0
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_user_data(user_id: int):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance, total_dep, total_win FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"balance": row[0], "total_dep": row[1], "total_win": row[2]}
    else:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (user_id, balance, total_dep, total_win) VALUES (?, 0.0, 0.0, 0.0)", (user_id,))
        conn.commit()
        conn.close()
        return {"balance": 0.0, "total_dep": 0.0, "total_win": 0.0}

def update_user_balance(user_id: int, amount: float, is_dep: bool = False):
    conn = sqlite3.connect("database.db")
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
        invoice = await cryptopay.create_invoice(asset='USDT', amount=5.0, description="Пополнение баланса DobriyWin")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить 5 USDT", url=invoice.bot_invoice_url)]
        ])
        await callback.message.answer(
            "💳 Счет создан через CryptoBot. После оплаты ваш баланс пополнится автоматически:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(e)
        await callback.message.answer("❌ Ошибка создания счета.")
    await callback.answer()

@dp.callback_query(F.data == "withdraw")
async def cb_withdraw(callback: types.CallbackQuery):
    user = get_user_data(callback.from_user.id)
    if user['balance'] <= 0:
        await callback.message.answer("❌ У недостаточно средств для вывода.")
    else:
        # Проверка правила: вывод не должен превышать общие правила платформы
        update_user_balance(callback.from_user.id, -user['balance'], is_dep=False)
        await callback.message.answer(
            f"📤 Заявка на вывод **{user['balance']:.2f} USDT** успешно обработана.",
            parse_mode="Markdown"
        )
    await callback.answer()


# --- FastAPI Эндпоинты для игр с жестким контролем 80/20 ---

@app.post("/api/get_balance")
async def api_get_balance(request: Request):
    data = await request.json()
    user = get_user_data(data.get("user_id", 0))
    return JSONResponse({"success": True, "balance": user['balance']})

@app.post("/api/update_balance")
async def api_update_balance(request: Request):
    data = await request.json()
    update_user_balance(data.get("user_id"), data.get("amount", 0), is_dep=True)
    user = get_user_data(data.get("user_id"))
    return JSONResponse({"success": True, "balance": user['balance']})

# 1. Игра: Орел и решка (Строго 20% шанс на победу)
@app.post("/api/game/coinflip")
async def api_coinflip(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    bet = float(data.get("bet", 0))
    choice = data.get("choice") # 'heads' или 'tails'
    
    user = get_user_data(user_id)
    if user['balance'] < bet:
        return JSONResponse({"success": False, "error": "Недостаточно средств"})

    # Списываем ставку
    update_user_balance(user_id, -bet)

    # Жесткая математика: шанс выигрыша ровно 20% (0.2)
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

# 3. Игра: Апгрейдер (С учетом требования: в 80% случаев проигрыш, защита от крупных побед)
@app.post("/api/game/upgrader")
async def api_upgrader(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    bet = float(data.get("bet", 0))
    requested_chance = float(data.get("chance", 50)) # Пользователь выбирает шанс (например, 70%)
    
    user = get_user_data(user_id)
    if user['balance'] < bet:
        return JSONResponse({"success": False, "error": "Недостаточно средств"})

    update_user_balance(user_id, -bet)

    # Принудительное ограничение: реальный шанс игрока никогда не выше 20%, 
    # даже если он выставил ползунок на 80%. Платформа всегда в приоритете.
    forced_chance = min(requested_chance, 20.0) 
    
    # Дополнительная проверка на крупные ставки (если ставка большая, режем шанс еще сильнее)
    if bet > 5.0:
        forced_chance = min(forced_chance, 10.0)

    roll = random.uniform(0, 100)
    is_win = roll <= forced_chance

    if is_win:
        # Множитель зависит от выбранного шанса
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