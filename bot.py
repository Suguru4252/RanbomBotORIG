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
BOT_TOKEN = "8703891124:AAFp8QR42TeKijiEMEOG5NUZEQaylokDDwU"

# Логирование
logging.basicConfig(level=logging.INFO)

# Создаем бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот для генерации картинок!\n"
        "Отправь мне любой текст и я создам изображение.\n\n"
        "Примеры: кот в космосе, красивый закат, робот"
    )

@dp.message()
async def generate(message: types.Message):
    # Сообщение о начале
    wait_msg = await message.answer("🎨 Генерирую картинку... ⏳")
    
    try:
        # Подготавливаем промпт
        prompt = message.text
        
        # Очищаем промпт для URL
        prompt_clean = prompt.replace(" ", "%20")
        prompt_clean = prompt_clean.replace("?", "")
        prompt_clean = prompt_clean.replace("!", "")
        prompt_clean = prompt_clean.replace(",", "")
        prompt_clean = prompt_clean.replace(".", "")
        
        # Формируем URL для Pollinations
        url = f"https://image.pollinations.ai/prompt/{prompt_clean}?width=1024&height=1024&nologo=true&model=flux"
        
        logging.info(f"Запрос к: {url}")
        
        # Скачиваем картинку
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=60) as response:
                logging.info(f"Статус ответа: {response.status}")
                
                if response.status == 200:
                    # Сохраняем картинку
                    filename = f"img_{uuid.uuid4()}.jpg"
                    async with aiofiles.open(filename, 'wb') as f:
                        await f.write(await response.read())
                    
                    # Проверяем размер файла
                    file_size = os.path.getsize(filename)
                    logging.info(f"Размер файла: {file_size} байт")
                    
                    if file_size > 1000:  # Если файл не пустой
                        # Отправляем пользователю
                        photo = FSInputFile(filename)
                        await message.reply_photo(
                            photo=photo,
                            caption=f"✅ Вот твоя картинка!\nЗапрос: {prompt}"
                        )
                        
                        # Удаляем файл
                        os.remove(filename)
                        await wait_msg.delete()
                    else:
                        await wait_msg.edit_text("❌ Получен пустой файл. Попробуй другой запрос.")
                        os.remove(filename)
                else:
                    # Если не получилось, пробуем другой вариант URL
                    backup_url = f"https://pollinations.ai/prompt/{prompt_clean}"
                    
                    async with session.get(backup_url, timeout=60) as backup_response:
                        if backup_response.status == 200:
                            filename = f"img_{uuid.uuid4()}.jpg"
                            async with aiofiles.open(filename, 'wb') as f:
                                await f.write(await backup_response.read())
                            
                            photo = FSInputFile(filename)
                            await message.reply_photo(
                                photo=photo,
                                caption=f"✅ Вот твоя картинка!\nЗапрос: {prompt}"
                            )
                            
                            os.remove(filename)
                            await wait_msg.delete()
                        else:
                            await wait_msg.edit_text(
                                f"❌ Ошибка {response.status}. Сервер Pollinations временно недоступен.\n"
                                f"Попробуй через 5 минут или измени запрос."
                            )
                            
    except asyncio.TimeoutError:
        await wait_msg.edit_text("❌ Превышено время ожидания. Сервер долго отвечает.")
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await wait_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def main():
    print("✅ Бот запущен на Bothost!")
    print("📱 Иди в Telegram и тестируй!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
