import logging
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

# 👉 НАСТРОЙКИ
TELEGRAM_BOT_TOKEN = "8814841234:AAFpuZPCSoGofMt7KopsG4XzZvdKIbOyL5g"
CRYPTO_BOT_TOKEN = "639499:AANlVeyFTk4dJ7z5PJvXfPXpITIfR9VVAOf"
WEB_APP_URL = "https://dobriywin.vercel.app" # Например, с Vercel

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
app = FastAPI()

CRYPTO_API_URL = "https://pay.crypt.bot/api/" # Рабочий URL Crypto Pay (или testnet-url для тестов)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть в DobriyWin", web_app=WebAppInfo(url=WEB_APP_URL))]
    ])
    await message.answer(
        "👋 Добро пожаловать в **dobriywin**!\n\n"
        "Пополняй баланс через CryptoBot, играй и выигрывай USDT:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# Эндпоинт, куда игра отправляет запрос на создание счета для пополнения
@app.post("/api/create_invoice")
async def create_invoice(request: Request):
    data = await request.json()
    amount = data.get("amount", 1)
    
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    payload = {
        "asset": "USDT",
        "amount": str(amount),
        "description": "Пополнение баланса в DobriyWin",
        "payload": f"user_deposit"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(f"{CRYPTO_API_URL}createInvoice", json=payload, headers=headers)
        result = response.json()
        
        if result.get("ok"):
            invoice = result["result"]
            return JSONResponse({"pay_url": invoice["pay_url"], "invoice_id": invoice["invoice_id"]})
        else:
            return JSONResponse({"error": "Не удалось создать счет в CryptoBot"}, status_code=400)

if __name__ == "__main__":
    import uvicorn
    # Запускаем локальный сервер (для тестов в продакшене нужен будет публичный хостинг с HTTPS, например Heroku, Render или VPS)
    uvicorn.run(app, host="0.0.0.0", port=8000)