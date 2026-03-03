import asyncio
import logging
import aiohttp
import aiofiles
import os
import uuid
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile

# ТВОЙ НОВЫЙ ТОКЕН (вставь сюда)
BOT_TOKEN = "8703891124:AAGYfu1MsclMc8e4ulVOTdNy-j1TbJN3CDc"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("👋 Отправь мне любой текст, и я сгенерирую картинку!")

@dp.message()
async def generate(message: types.Message):
    wait_msg = await message.answer("🎨 Генерирую картинку... ⏳")
    
    try:
        prompt = message.text.replace(" ", "%20")
        url = f"https://image.pollinations.ai/prompt/{prompt}?width=1024&height=1024&nologo=true"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as resp:
                if resp.status == 200:
                    filename = f"{uuid.uuid4()}.jpg"
                    async with aiofiles.open(filename, 'wb') as f:
                        await f.write(await resp.read())
                    
                    photo = FSInputFile(filename)
                    await message.reply_photo(photo, caption=f"✅ Готово!")
                    
                    os.remove(filename)
                    await wait_msg.delete()
                else:
                    await wait_msg.edit_text(f"❌ Ошибка {resp.status}. Попробуй другой запрос.")
    except Exception as e:
        await wait_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def main():
    print("✅ Бот запущен на Bothost!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
