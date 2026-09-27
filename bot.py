import os
import logging
import asyncio
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

# 👉 Читаем настройки из переменных окружения Render
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN")
WEB_APP_URL = "https://dobriywin.onrender.com"  # Ваша актуальная ссылка на Render

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None
dp = Dispatcher()
app = FastAPI()

CRYPTO_API_URL = "https://pay.crypt.bot/api/"

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
    if not CRYPTO_BOT_TOKEN:
        return JSONResponse({"error": "CryptoBot token not configured"}, status_code=500)
        
    data = await request.json()
    amount = data.get("amount", 1)
     
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    payload = {
        "asset": "USDT",
        "amount": str(amount),
        "description": "Пополнение баланса в DobriyWin",
        "payload": "user_deposit"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(f"{CRYPTO_API_URL}createInvoice", json=payload, headers=headers)
        result = response.json()
         
        if result.get("ok"):
            invoice = result["result"]
            return JSONResponse({"pay_url": invoice["pay_url"], "invoice_id": invoice["invoice_id"]})
        else:
            return JSONResponse({"error": "Не удалось создать счет в CryptoBot"}, status_code=400)

# Запускаем фоновый поллинг бота при старте FastAPI приложения
@app.on_event("startup")
async def on_startup():
    if bot:
        # Убираем старые вебхуки, если они были, и запускаем polling в фоне
        await bot.delete_webhook(drop_pending_updates=True)
        asyncio.create_task(dp.start_polling(bot))
        logging.info("Telegram bot started successfully via polling!")
    else:
        logging.error("BOT_TOKEN is missing! Telegram bot could not start.")
