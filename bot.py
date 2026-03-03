import asyncio
import logging
import aiohttp
import aiofiles
import os
import uuid
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile

# ТВОЙ ТОКЕН
BOT_TOKEN = "8703891124:AAFp8QR42TeKijiEMEOG5NUZEQaylokDDwU"

# Логирование
logging.basicConfig(level=logging.INFO)

# Создаем бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот для генерации картинок!\n"
        "Просто напиши что хочешь увидеть и я создам картинку!"
    )

@dp.message()
async def generate_image(message: types.Message):
    # Отправляем сообщение что начали генерацию
    msg = await message.answer("🖼 Генерирую картинку... подожди 10-20 секунд")
    
    try:
        # Формируем запрос к Pollinations
        prompt = message.text.replace(" ", "%20")
        url = f"https://image.pollinations.ai/prompt/{prompt}?width=1024&height=1024&nologo=true"
        
        # Скачиваем картинку
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    # Сохраняем картинку
                    filename = f"{uuid.uuid4()}.jpg"
                    async with aiofiles.open(filename, 'wb') as f:
                        await f.write(await resp.read())
                    
                    # Отправляем пользователю
                    photo = FSInputFile(filename)
                    await message.reply_photo(photo, caption=f"Вот твоя картинка: {message.text}")
                    
                    # Удаляем файл
                    os.remove(filename)
                    await msg.delete()
                else:
                    await msg.edit_text("❌ Ошибка при генерации. Попробуй другой запрос.")
                    
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)}")

async def main():
    print("✅ Бот запущен на Bothost!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
