import asyncio
import aiohttp
import aiofiles
import os
import uuid
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile

# Токен берется из переменных окружения (для безопасности)
API_TOKEN = os.getenv('BOT_TOKEN')

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

async def get_pollinations_image(prompt):
    prompt_clean = prompt.replace(' ', '%20')
    url = f"https://image.pollinations.ai/prompt/{prompt_clean}?width=1024&height=1024&nologo=true"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.read()
    return None

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.reply(
        "👋 Привет! Я бот для генерации картинок через Pollinations.ai!\n\n"
        "Просто напиши что хочешь увидеть, например:\n"
        "• cat in space\n"
        "• beautiful sunset\n"
        "• futuristic city"
    )

@dp.message()
async def generate(message: types.Message):
    wait_msg = await message.reply("🎨 Генерирую картинку... Подожди немного ⏳")
    
    try:
        image_data = await get_pollinations_image(message.text)
        
        if image_data:
            filename = f"{uuid.uuid4()}.jpg"
            async with aiofiles.open(filename, 'wb') as f:
                await f.write(image_data)
            
            photo = FSInputFile(filename)
            await message.reply_photo(
                photo=photo,
                caption=f"✅ Вот твоя картинка по запросу: {message.text}"
            )
            
            os.remove(filename)
            await wait_msg.delete()
        else:
            await wait_msg.edit_text("❌ Не удалось сгенерировать картинку. Попробуй другой запрос.")
            
    except Exception as e:
        await wait_msg.edit_text(f"❌ Ошибка: {str(e)}")

async def main():
    print("🚀 Бот на Pollinations.ai запущен!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
