import asyncio
import logging
import aiohttp
import aiofiles
import os
import uuid
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile

# Настройки для Bothost
BOT_TOKEN = "8703891124:AAFp8QR42TeKijiEMEOG5NUZEQaylokDDwU"  # Твой токен

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Функция для генерации через Pollinations.ai
async def generate_image(prompt):
    """Генерация изображения через Pollinations.ai"""
    try:
        # Очищаем промпт для URL
        clean_prompt = prompt.replace(' ', '%20')
        
        # URL для генерации (без логотипа, хорошее качество)
        url = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=1024&height=1024&nologo=true"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    logging.error(f"Ошибка HTTP: {response.status}")
                    return None
    except Exception as e:
        logging.error(f"Ошибка генерации: {e}")
        return None

# Команда /start
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот для генерации картинок!\n\n"
        "📝 Отправь мне описание того, что хочешь увидеть\n"
        "🎨 Я создам изображение через Pollinations.ai\n"
        "⏳ Обычно ждать 10-20 секунд\n\n"
        "Примеры:\n"
        "• красивый закат на море\n"
        "• кот в космосе\n"
        "• futuristic city cyberpunk"
    )

# Команда /help
@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "🤔 **Как пользоваться:**\n"
        "1. Напиши текст на русском или английском\n"
        "2. Подожди немного\n"
        "3. Получи картинку!\n\n"
        "💡 **Советы:**\n"
        "• На английском картинки получаются лучше\n"
        "• Чем подробнее опишешь, тем точнее результат\n"
        "• Можно указывать стиль: фото, рисунок, 3D\n\n"
        "❓ Если не работает - напиши /start"
    )

# Обработка текстовых сообщений
@dp.message()
async def handle_text(message: types.Message):
    prompt = message.text
    
    # Проверка длины запроса
    if len(prompt) < 3:
        await message.answer("❌ Слишком короткий запрос. Опиши подробнее!")
        return
    
    # Отправляем сообщение о начале генерации
    wait_msg = await message.answer("🎨 **Генерирую картинку...**\n⏳ Это займёт примерно 15 секунд")
    
    try:
        # Генерируем изображение
        image_data = await generate_image(prompt)
        
        if image_data:
            # Сохраняем во временный файл
            filename = f"img_{uuid.uuid4()}.jpg"
            async with aiofiles.open(filename, 'wb') as f:
                await f.write(image_data)
            
            # Отправляем фото
            photo = FSInputFile(filename)
            await message.reply_photo(
                photo=photo,
                caption=f"✅ **Готово!**\n\nЗапрос: {prompt}"
            )
            
            # Удаляем временный файл
            os.remove(filename)
            
            # Удаляем сообщение о генерации
            await wait_msg.delete()
        else:
            await wait_msg.edit_text(
                "❌ **Не удалось создать картинку**\n\n"
                "Попробуй:\n"
                "• Изменить запрос\n"
                "• Написать на английском\n"
                "• Отправить запрос ещё раз"
            )
    
    except Exception as e:
        await wait_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

# Запуск бота
async def main():
    print("✅ Бот запущен на Bothost!")
    print("📱 Бот готов к работе")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
