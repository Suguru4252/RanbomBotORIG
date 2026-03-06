#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Bot для генерации изображений по текстовому описанию
Использует бесплатный Pollinations API
"""

import asyncio
import logging
import sqlite3
import aiohttp
import random
from datetime import datetime, timedelta
from io import BytesIO
from typing import Dict, List, Optional, Tuple

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton,
    CallbackQuery, InputFile, BufferedInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

# ==================== НАСТРОЙКИ ====================

# Токен бота (получи у @BotFather)
BOT_TOKEN = "8703891124:AAFp8QR42TeKijiEMEOG5NUZEQaylokDDwU"  # <--- ЗАМЕНИ НА СВОЙ ТОКЕН!

# ID администратора (для уведомлений)
ADMIN_ID = 5596589260  # <--- ЗАМЕНИ НА СВОЙ ID (узнай у @userinfobot)

# Настройки генерации
DEFAULT_IMAGE_SIZE = "512x512"  # размер по умолчанию
DEFAULT_IMAGE_STYLE = "реализм"  # стиль по умолчанию
MAX_GENERATIONS_PER_DAY = 20  # лимит генераций в день на пользователя
HISTORY_LIMIT = 5  # сколько последних запросов сохранять

# API для генерации (бесплатный)
POLLINATIONS_API_URL = "https://image.pollinations.ai/prompt/{}"

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ==================== БАЗА ДАННЫХ ====================

class Database:
    """Класс для работы с SQLite базой данных"""
    
    def __init__(self, db_name: str = "image_bot.db"):
        self.db_name = db_name
        self.init_db()
    
    def get_connection(self):
        """Получить соединение с БД"""
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        """Инициализация таблиц"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_generations INTEGER DEFAULT 0,
                    preferred_size TEXT DEFAULT '512x512',
                    preferred_style TEXT DEFAULT 'реализм',
                    is_admin INTEGER DEFAULT 0,
                    is_banned INTEGER DEFAULT 0
                )
            ''')
            
            # Таблица генераций
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS generations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    prompt TEXT,
                    style TEXT,
                    size TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Таблица для статистики по дням
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    date DATE,
                    count INTEGER DEFAULT 0,
                    UNIQUE(user_id, date)
                )
            ''')
            
            conn.commit()
            
            # Добавляем админа, если его нет
            if ADMIN_ID:
                cursor.execute(
                    "INSERT OR IGNORE INTO users (user_id, is_admin) VALUES (?, 1)",
                    (ADMIN_ID,)
                )
                conn.commit()
    
    # ===== ПОЛЬЗОВАТЕЛИ =====
    
    def get_or_create_user(self, user_id: int, username: str = None, 
                           first_name: str = None, last_name: str = None) -> dict:
        """Получить или создать пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,)
            )
            user = cursor.fetchone()
            
            if not user:
                cursor.execute('''
                    INSERT INTO users (user_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, username, first_name, last_name))
                conn.commit()
                
                cursor.execute(
                    "SELECT * FROM users WHERE user_id = ?",
                    (user_id,)
                )
                user = cursor.fetchone()
            else:
                # Обновляем last_active
                cursor.execute(
                    "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
                    (user_id,)
                )
                conn.commit()
            
            return dict(user) if user else None
    
    def update_user_preferences(self, user_id: int, size: str = None, style: str = None):
        """Обновить предпочтения пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if size:
                cursor.execute(
                    "UPDATE users SET preferred_size = ? WHERE user_id = ?",
                    (size, user_id)
                )
            if style:
                cursor.execute(
                    "UPDATE users SET preferred_style = ? WHERE user_id = ?",
                    (style, user_id)
                )
            conn.commit()
    
    def is_user_banned(self, user_id: int) -> bool:
        """Проверить, забанен ли пользователь"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT is_banned FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            return row and row['is_banned'] == 1 if row else False
    
    def ban_user(self, user_id: int, admin_id: int) -> bool:
        """Забанить пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET is_banned = 1 WHERE user_id = ?",
                (user_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def unban_user(self, user_id: int) -> bool:
        """Разбанить пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET is_banned = 0 WHERE user_id = ?",
                (user_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def is_admin(self, user_id: int) -> bool:
        """Проверить, является ли пользователь админом"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT is_admin FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            return row and row['is_admin'] == 1 if row else False
    
    # ===== ГЕНЕРАЦИИ =====
    
    def add_generation(self, user_id: int, prompt: str, style: str, size: str) -> bool:
        """Добавить запись о генерации"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Обновляем общий счетчик
            cursor.execute('''
                UPDATE users 
                SET total_generations = total_generations + 1,
                    last_active = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (user_id,))
            
            # Добавляем запись в generations
            cursor.execute('''
                INSERT INTO generations (user_id, prompt, style, size)
                VALUES (?, ?, ?, ?)
            ''', (user_id, prompt, style, size))
            
            # Обновляем дневную статистику
            today = datetime.now().date().isoformat()
            cursor.execute('''
                INSERT INTO daily_stats (user_id, date, count)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id, date) 
                DO UPDATE SET count = count + 1
            ''', (user_id, today))
            
            conn.commit()
            return True
    
    def get_user_history(self, user_id: int, limit: int = 5) -> List[dict]:
        """Получить историю генераций пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT prompt, style, size, created_at
                FROM generations
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_today_count(self, user_id: int) -> int:
        """Получить количество генераций за сегодня"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            today = datetime.now().date().isoformat()
            cursor.execute('''
                SELECT count FROM daily_stats
                WHERE user_id = ? AND date = ?
            ''', (user_id, today))
            row = cursor.fetchone()
            return row['count'] if row else 0
    
    def get_user_stats(self, user_id: int) -> dict:
        """Получить статистику пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT total_generations, preferred_size, preferred_style
                FROM users WHERE user_id = ?
            ''', (user_id,))
            user = cursor.fetchone()
            
            if not user:
                return {}
            
            today_count = self.get_today_count(user_id)
            
            cursor.execute('''
                SELECT COUNT(*) as count FROM generations
                WHERE user_id = ?
            ''', (user_id,))
            total = cursor.fetchone()
            
            return {
                'total': total['count'] if total else 0,
                'today': today_count,
                'preferred_size': user['preferred_size'],
                'preferred_style': user['preferred_style']
            }
    
    # ===== АДМИН ФУНКЦИИ =====
    
    def get_all_users(self) -> List[dict]:
        """Получить всех пользователей"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, username, first_name, total_generations,
                       last_active, is_banned, is_admin
                FROM users ORDER BY last_active DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_stats(self) -> dict:
        """Получить общую статистику"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) as count FROM users")
            total_users = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM generations")
            total_generations = cursor.fetchone()['count']
            
            cursor.execute('''
                SELECT COUNT(DISTINCT user_id) as count 
                FROM daily_stats 
                WHERE date = date('now')
            ''')
            active_today = cursor.fetchone()['count']
            
            return {
                'total_users': total_users,
                'total_generations': total_generations,
                'active_today': active_today
            }

# Инициализация базы данных
db = Database()

# ==================== СОСТОЯНИЯ FSM ====================

class GenerationStates(StatesGroup):
    waiting_for_prompt = State()

# ==================== КЛАВИАТУРЫ ====================

def get_main_keyboard(user_id: int = None) -> ReplyKeyboardMarkup:
    """Главная клавиатура"""
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="🎨 Сгенерировать"))
    builder.add(KeyboardButton(text="📊 Моя статистика"))
    builder.add(KeyboardButton(text="⚙️ Настройки"))
    builder.add(KeyboardButton(text="🆘 Помощь"))
    
    if user_id and db.is_admin(user_id):
        builder.add(KeyboardButton(text="👑 Админ панель"))
    
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отмены"""
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="❌ Отмена"))
    return builder.as_markup(resize_keyboard=True)

def get_styles_inline_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора стиля"""
    styles = [
        ("🎨 Реализм", "реализм"),
        ("🌸 Аниме", "аниме"),
        ("🧙 Фэнтези", "фэнтези"),
        ("🤖 Киберпанк", "киберпанк"),
        ("✨ 3D-рендер", "3d"),
        ("🖼️ Масляная живопись", "живопись"),
        ("🎯 Скетч", "скетч"),
        ("🌌 Сюрреализм", "сюрреализм")
    ]
    
    builder = InlineKeyboardBuilder()
    for text, style in styles:
        builder.add(InlineKeyboardButton(
            text=text, 
            callback_data=f"style_{style}"
        ))
    builder.adjust(2)
    return builder.as_markup()

def get_sizes_inline_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора размера"""
    sizes = [
        ("🟦 512x512", "512x512"),
        ("🟨 768x768", "768x768"),
        ("🟥 1024x1024", "1024x1024")
    ]
    
    builder = InlineKeyboardBuilder()
    for text, size in sizes:
        builder.add(InlineKeyboardButton(
            text=text,
            callback_data=f"size_{size}"
        ))
    builder.adjust(1)
    return builder.as_markup()

def get_generation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для генерации"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="🎨 Новый промпт",
        callback_data="new_prompt"
    ))
    builder.add(InlineKeyboardButton(
        text="🔄 Случайный промпт",
        callback_data="random_prompt"
    ))
    builder.add(InlineKeyboardButton(
        text="📋 История",
        callback_data="show_history"
    ))
    builder.add(InlineKeyboardButton(
        text="⚙️ Настройки стиля",
        callback_data="style_settings"
    ))
    builder.adjust(1)
    return builder.as_markup()

def get_history_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для истории"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="🎨 Новая генерация",
        callback_data="new_prompt"
    ))
    builder.add(InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_main"
    ))
    return builder.as_markup()

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для админ панели"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="📊 Статистика бота",
        callback_data="admin_stats"
    ))
    builder.add(InlineKeyboardButton(
        text="👥 Список пользователей",
        callback_data="admin_users"
    ))
    builder.add(InlineKeyboardButton(
        text="🔍 Найти пользователя",
        callback_data="admin_find"
    ))
    builder.add(InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_main"
    ))
    builder.adjust(1)
    return builder.as_markup()

def get_user_actions_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура действий с пользователем"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="📊 Статистика",
        callback_data=f"user_stats_{user_id}"
    ))
    
    if db.is_user_banned(user_id):
        builder.add(InlineKeyboardButton(
            text="✅ Разбанить",
            callback_data=f"unban_{user_id}"
        ))
    else:
        builder.add(InlineKeyboardButton(
            text="⛔ Забанить",
            callback_data=f"ban_{user_id}"
        ))
    
    builder.add(InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="admin_users"
    ))
    builder.adjust(1)
    return builder.as_markup()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def format_prompt_with_style(prompt: str, style: str) -> str:
    """Добавить стиль к промпту"""
    style_map = {
        "реализм": "photorealistic, highly detailed, 8k, realistic",
        "аниме": "anime style, manga, anime art, japanese animation",
        "фэнтези": "fantasy art, magical, mythical, fantasy landscape, epic",
        "киберпанк": "cyberpunk, neon, futuristic, dark city, blade runner style",
        "3d": "3d render, octane render, blender, 3d model, cgi, 3d art",
        "живопись": "oil painting, canvas, masterpiece, classical art, painterly",
        "скетч": "sketch, drawing, pencil sketch, line art, monochrome",
        "сюрреализм": "surreal, dreamlike, surrealism, dali style, bizarre"
    }
    
    style_suffix = style_map.get(style, style)
    return f"{prompt}, {style_suffix}"

def generate_random_prompt() -> str:
    """Сгенерировать случайный промпт для вдохновения"""
    prompts = [
        "киберпанк город в неоновых огнях под дождем",
        "дракон летящий над средневековым замком",
        "космический пейзаж с туманностью и звездами",
        "волшебный лес с светящимися грибами",
        "футуристический робот в стиле ретро",
        "подводный мир с разноцветными рыбами и кораллами",
        "горный пейзаж с водопадом на закате",
        "абстрактная композиция в стиле Kandinsky",
        "портрет девушки в стиле аниме",
        "заброшенный дом в тумане, хоррор стиль",
        "космическая станция на орбите Юпитера",
        "средневековый рыцарь в бою",
        "магическая библиотека с летающими книгами",
        "неоновый самурай в киберпанк городе",
        "стимпанк дирижабль над городом",
        "инопланетный пейзаж с двумя лунами",
        "волшебница, создающая заклинание",
        "футуристический автомобиль на улицах Токио",
        "механический дракон из металла",
        "аниме девушка с цветущей сакурой"
    ]
    return random.choice(prompts)

async def generate_image(prompt: str) -> Optional[BytesIO]:
    """Сгенерировать изображение через Pollinations API"""
    try:
        # Кодируем промпт для URL
        import urllib.parse
        encoded_prompt = urllib.parse.quote(prompt)
        
        # Формируем URL с параметрами
        # Добавляем параметры для лучшего качества
        url = POLLINATIONS_API_URL.format(encoded_prompt)
        url += "?width=1024&height=1024&nologo=true&model=flux"
        
        logger.info(f"Генерация изображения для промпта: {prompt[:50]}...")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=60) as response:
                if response.status == 200:
                    image_data = await response.read()
                    return BytesIO(image_data)
                else:
                    logger.error(f"Ошибка API: {response.status}")
                    return None
    except asyncio.TimeoutError:
        logger.error("Таймаут при генерации изображения")
        return None
    except Exception as e:
        logger.error(f"Ошибка при генерации: {e}")
        return None

# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    
    # Сбрасываем состояние
    await state.clear()
    
    # Проверяем бан
    if db.is_user_banned(user_id):
        await message.answer("⛔ Вы заблокированы в боте.")
        return
    
    # Регистрируем пользователя
    user = db.get_or_create_user(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )
    
    welcome_text = (
        "🎨 **Добро пожаловать в Image Generator Bot!**\n\n"
        "Я могу создать любое изображение по вашему текстовому описанию. "
        "Просто отправь мне промпт, и я сгенерирую картинку.\n\n"
        "**Примеры запросов:**\n"
        "• киберпанк город в неоновых огнях\n"
        "• дракон летящий над замком\n"
        "• космический пейзаж с туманностью\n"
        "• аниме девушка с цветущей сакурой\n\n"
        "**Команды:**\n"
        "🎨 /generate - начать генерацию\n"
        "📊 /stats - моя статистика\n"
        "⚙️ /settings - настройки\n"
        "🆘 /help - помощь"
    )
    
    await message.answer(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user_id)
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message, state: FSMContext):
    """Обработчик команды /help"""
    await state.clear()
    
    help_text = (
        "🆘 **Помощь по боту**\n\n"
        "**Как пользоваться:**\n"
        "1️⃣ Нажми /generate или кнопку 'Сгенерировать'\n"
        "2️⃣ Отправь текстовое описание того, что хочешь увидеть\n"
        "3️⃣ Подожди немного, пока я создаю картинку\n\n"
        "**Советы для лучших результатов:**\n"
        "• Будь конкретным: 'красивый закат' → 'закат над горами с оранжевым небом и отражением в озере'\n"
        "• Добавляй стили: 'в стиле аниме', 'фотореалистичный', 'масляная живопись'\n"
        "• Указывай детали: цвета, освещение, окружение\n\n"
        "**Настройки:**\n"
        "• /settings - изменить стиль или размер изображения\n"
        "• /stats - посмотреть свою статистику\n\n"
        "**Лимиты:**\n"
        "• Максимум {MAX_GENERATIONS_PER_DAY} генераций в день на пользователя\n"
        "• Бесплатный сервис, но есть очередь при высокой нагрузке"
    ).format(MAX_GENERATIONS_PER_DAY=MAX_GENERATIONS_PER_DAY)
    
    await message.answer(help_text, parse_mode="Markdown")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message, state: FSMContext):
    """Обработчик команды /stats"""
    user_id = message.from_user.id
    await state.clear()
    
    stats = db.get_user_stats(user_id)
    
    if not stats:
        await message.answer("❌ Статистика не найдена")
        return
    
    stats_text = (
        "📊 **Ваша статистика**\n\n"
        f"• Всего генераций: **{stats['total']}**\n"
        f"• Сегодня: **{stats['today']}** / {MAX_GENERATIONS_PER_DAY}\n"
        f"• Осталось сегодня: **{MAX_GENERATIONS_PER_DAY - stats['today']}**\n"
        f"• Любимый стиль: **{stats['preferred_style']}**\n"
        f"• Любимый размер: **{stats['preferred_size']}**"
    )
    
    await message.answer(stats_text, parse_mode="Markdown")

@dp.message(Command("settings"))
async def cmd_settings(message: types.Message, state: FSMContext):
    """Обработчик команды /settings"""
    user_id = message.from_user.id
    await state.clear()
    
    user = db.get_or_create_user(user_id)
    
    settings_text = (
        "⚙️ **Настройки генерации**\n\n"
        f"Текущий стиль: **{user['preferred_style']}**\n"
        f"Текущий размер: **{user['preferred_size']}**\n\n"
        "Выберите параметр для изменения:"
    )
    
    # Создаем клавиатуру настроек
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="🎨 Изменить стиль",
        callback_data="style_settings"
    ))
    builder.add(InlineKeyboardButton(
        text="📏 Изменить размер",
        callback_data="size_settings"
    ))
    builder.add(InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_main"
    ))
    builder.adjust(1)
    
    await message.answer(settings_text, parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.message(Command("generate"))
async def cmd_generate(message: types.Message, state: FSMContext):
    """Обработчик команды /generate"""
    user_id = message.from_user.id
    await state.clear()
    
    if db.is_user_banned(user_id):
        await message.answer("⛔ Вы заблокированы в боте.")
        return
    
    # Проверяем лимит
    today_count = db.get_today_count(user_id)
    if today_count >= MAX_GENERATIONS_PER_DAY:
        await message.answer(
            f"❌ Вы исчерпали лимит на сегодня ({MAX_GENERATIONS_PER_DAY}).\n"
            f"Завтра можно будет снова генерировать!"
        )
        return
    
    await message.answer(
        "🎨 **Генерация изображения**\n\n"
        "Отправьте текстовое описание того, что вы хотите увидеть.\n\n"
        "Например:\n"
        "• 'киберпанк город в неоновых огнях'\n"
        "• 'дракон летящий над средневековым замком'\n"
        "• 'аниме девушка с цветущей сакурой'",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(GenerationStates.waiting_for_prompt)

# ==================== ОБРАБОТЧИКИ СООБЩЕНИЙ ====================

@dp.message(F.text == "🎨 Сгенерировать")
async def button_generate(message: types.Message, state: FSMContext):
    """Обработчик кнопки Сгенерировать"""
    await cmd_generate(message, state)

@dp.message(F.text == "📊 Моя статистика")
async def button_stats(message: types.Message, state: FSMContext):
    """Обработчик кнопки Моя статистика"""
    await cmd_stats(message, state)

@dp.message(F.text == "⚙️ Настройки")
async def button_settings(message: types.Message, state: FSMContext):
    """Обработчик кнопки Настройки"""
    await cmd_settings(message, state)

@dp.message(F.text == "🆘 Помощь")
async def button_help(message: types.Message, state: FSMContext):
    """Обработчик кнопки Помощь"""
    await cmd_help(message, state)

@dp.message(F.text == "👑 Админ панель")
async def button_admin(message: types.Message, state: FSMContext):
    """Обработчик кнопки Админ панель"""
    user_id = message.from_user.id
    
    if not db.is_admin(user_id):
        await message.answer("❌ У вас нет доступа к админ панели.")
        return
    
    await state.clear()
    
    stats = db.get_stats()
    
    admin_text = (
        "👑 **Админ панель**\n\n"
        f"📊 **Общая статистика:**\n"
        f"• Всего пользователей: **{stats['total_users']}**\n"
        f"• Всего генераций: **{stats['total_generations']}**\n"
        f"• Активных сегодня: **{stats['active_today']}**\n\n"
        "Выберите действие:"
    )
    
    await message.answer(admin_text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

@dp.message(F.text == "❌ Отмена")
async def button_cancel(message: types.Message, state: FSMContext):
    """Обработчик кнопки Отмена"""
    await state.clear()
    await message.answer(
        "Действие отменено.",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.message(GenerationStates.waiting_for_prompt)
async def process_generation_prompt(message: types.Message, state: FSMContext):
    """Обработка промпта для генерации"""
    user_id = message.from_user.id
    
    # Проверяем отмену
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer(
            "Генерация отменена.",
            reply_markup=get_main_keyboard(user_id)
        )
        return
    
    # Проверяем лимит
    today_count = db.get_today_count(user_id)
    if today_count >= MAX_GENERATIONS_PER_DAY:
        await state.clear()
        await message.answer(
            f"❌ Вы исчерпали лимит на сегодня ({MAX_GENERATIONS_PER_DAY}).",
            reply_markup=get_main_keyboard(user_id)
        )
        return
    
    prompt = message.text
    
    if len(prompt) < 3:
        await message.answer(
            "❌ Слишком короткий промпт. Опишите подробнее (минимум 3 символа):"
        )
        return
    
    if len(prompt) > 1000:
        await message.answer(
            "❌ Слишком длинный промпт. Максимум 1000 символов."
        )
        return
    
    # Получаем настройки пользователя
    user = db.get_or_create_user(user_id)
    style = user['preferred_style']
    size = user['preferred_size']
    
    # Отправляем сообщение о начале генерации
    wait_msg = await message.answer(
        f"🎨 **Генерация изображения...**\n\n"
        f"Промпт: _{prompt[:100]}{'...' if len(prompt) > 100 else ''}_\n"
        f"Стиль: {style}\n"
        f"Размер: {size}\n\n"
        f"⏳ Это займет несколько секунд...",
        parse_mode="Markdown"
    )
    
    # Форматируем промпт со стилем
    full_prompt = format_prompt_with_style(prompt, style)
    
    # Генерируем изображение
    image_bytes = await generate_image(full_prompt)
    
    if image_bytes:
        # Сохраняем в БД
        db.add_generation(user_id, prompt, style, size)
        
        # Отправляем изображение
        try:
            await message.answer_photo(
                photo=BufferedInputFile(
                    file=image_bytes.getvalue(),
                    filename="generated.jpg"
                ),
                caption=(
                    f"✅ **Изображение готово!**\n\n"
                    f"🎨 Промпт: {prompt}\n"
                    f"✨ Стиль: {style}\n"
                    f"📏 Размер: {size}\n"
                    f"📊 Осталось сегодня: {MAX_GENERATIONS_PER_DAY - today_count - 1}"
                ),
                parse_mode="Markdown",
                reply_markup=get_generation_keyboard()
            )
            
            # Удаляем сообщение о загрузке
            await wait_msg.delete()
            
        except Exception as e:
            logger.error(f"Ошибка при отправке: {e}")
            await wait_msg.edit_text(
                f"❌ Ошибка при отправке изображения. Попробуйте позже.",
                reply_markup=get_main_keyboard(user_id)
            )
    else:
        await wait_msg.edit_text(
            "❌ Не удалось сгенерировать изображение. Попробуйте другой промпт или позже.",
            reply_markup=get_main_keyboard(user_id)
        )
    
    await state.clear()

# ==================== ОБРАБОТЧИКИ CALLBACK ====================

@dp.callback_query(F.data == "new_prompt")
async def callback_new_prompt(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки Новый промпт"""
    await callback.answer()
    await cmd_generate(callback.message, state)

@dp.callback_query(F.data == "random_prompt")
async def callback_random_prompt(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки Случайный промпт"""
    await callback.answer()
    
    random_prompt = generate_random_prompt()
    
    # Отправляем сообщение, что будем использовать случайный промпт
    await callback.message.answer(
        f"🎲 **Случайный промпт:**\n\n"
        f"_{random_prompt}_\n\n"
        f"Начинаю генерацию..."
    )
    
    # Запускаем генерацию
    user_id = callback.from_user.id
    
    # Проверяем лимит
    today_count = db.get_today_count(user_id)
    if today_count >= MAX_GENERATIONS_PER_DAY:
        await callback.message.answer(
            f"❌ Вы исчерпали лимит на сегодня ({MAX_GENERATIONS_PER_DAY})."
        )
        return
    
    # Получаем настройки пользователя
    user = db.get_or_create_user(user_id)
    style = user['preferred_style']
    size = user['preferred_size']
    
    # Форматируем промпт со стилем
    full_prompt = format_prompt_with_style(random_prompt, style)
    
    # Генерируем изображение
    wait_msg = await callback.message.answer("⏳ Генерация...")
    image_bytes = await generate_image(full_prompt)
    
    if image_bytes:
        db.add_generation(user_id, random_prompt, style, size)
        
        await callback.message.answer_photo(
            photo=BufferedInputFile(
                file=image_bytes.getvalue(),
                filename="generated.jpg"
            ),
            caption=(
                f"✅ **Изображение готово!**\n\n"
                f"🎨 Промпт: {random_prompt}\n"
                f"✨ Стиль: {style}\n"
                f"📏 Размер: {size}"
            ),
            parse_mode="Markdown",
            reply_markup=get_generation_keyboard()
        )
        await wait_msg.delete()
    else:
        await wait_msg.edit_text(
            "❌ Не удалось сгенерировать изображение. Попробуйте позже."
        )

@dp.callback_query(F.data == "show_history")
async def callback_show_history(callback: CallbackQuery):
    """Обработчик кнопки История"""
    await callback.answer()
    
    user_id = callback.from_user.id
    history = db.get_user_history(user_id, HISTORY_LIMIT)
    
    if not history:
        await callback.message.answer(
            "📋 У вас пока нет истории генераций.",
            reply_markup=get_history_keyboard()
        )
        return
    
    history_text = "📋 **Последние генерации:**\n\n"
    
    for i, item in enumerate(history, 1):
        history_text += f"{i}. **{item['prompt'][:50]}**...\n"
        history_text += f"   ✨ {item['style']} | 📏 {item['size']}\n"
        history_text += f"   🕐 {item['created_at'][:16]}\n\n"
    
    await callback.message.answer(history_text, parse_mode="Markdown", reply_markup=get_history_keyboard())

@dp.callback_query(F.data == "style_settings")
async def callback_style_settings(callback: CallbackQuery):
    """Обработчик кнопки настроек стиля"""
    await callback.answer()
    
    user = db.get_or_create_user(callback.from_user.id)
    
    await callback.message.edit_text(
        f"🎨 **Выберите стиль генерации**\n\n"
        f"Текущий стиль: **{user['preferred_style']}**",
        parse_mode="Markdown",
        reply_markup=get_styles_inline_keyboard()
    )

@dp.callback_query(F.data == "size_settings")
async def callback_size_settings(callback: CallbackQuery):
    """Обработчик кнопки настроек размера"""
    await callback.answer()
    
    user = db.get_or_create_user(callback.from_user.id)
    
    await callback.message.edit_text(
        f"📏 **Выберите размер изображения**\n\n"
        f"Текущий размер: **{user['preferred_size']}**",
        parse_mode="Markdown",
        reply_markup=get_sizes_inline_keyboard()
    )

@dp.callback_query(F.data.startswith("style_"))
async def callback_set_style(callback: CallbackQuery):
    """Обработчик выбора стиля"""
    style = callback.data.replace("style_", "")
    
    db.update_user_preferences(callback.from_user.id, style=style)
    
    await callback.answer(f"✅ Стиль изменен на: {style}")
    
    # Возвращаемся в настройки
    user = db.get_or_create_user(callback.from_user.id)
    
    settings_text = (
        "⚙️ **Настройки генерации**\n\n"
        f"Текущий стиль: **{user['preferred_style']}**\n"
        f"Текущий размер: **{user['preferred_size']}**\n\n"
        "Выберите параметр для изменения:"
    )
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="🎨 Изменить стиль",
        callback_data="style_settings"
    ))
    builder.add(InlineKeyboardButton(
        text="📏 Изменить размер",
        callback_data="size_settings"
    ))
    builder.add(InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_main"
    ))
    builder.adjust(1)
    
    await callback.message.edit_text(
        settings_text,
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data.startswith("size_"))
async def callback_set_size(callback: CallbackQuery):
    """Обработчик выбора размера"""
    size = callback.data.replace("size_", "")
    
    db.update_user_preferences(callback.from_user.id, size=size)
    
    await callback.answer(f"✅ Размер изменен на: {size}")
    
    # Возвращаемся в настройки
    user = db.get_or_create_user(callback.from_user.id)
    
    settings_text = (
        "⚙️ **Настройки генерации**\n\n"
        f"Текущий стиль: **{user['preferred_style']}**\n"
        f"Текущий размер: **{user['preferred_size']}**\n\n"
        "Выберите параметр для изменения:"
    )
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="🎨 Изменить стиль",
        callback_data="style_settings"
    ))
    builder.add(InlineKeyboardButton(
        text="📏 Изменить размер",
        callback_data="size_settings"
    ))
    builder.add(InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_main"
    ))
    builder.adjust(1)
    
    await callback.message.edit_text(
        settings_text,
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "back_to_main")
async def callback_back_to_main(callback: CallbackQuery, state: FSMContext):
    """Обработчик возврата в главное меню"""
    await callback.answer()
    await state.clear()
    
    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=get_main_keyboard(callback.from_user.id)
    )

# ==================== АДМИН ОБРАБОТЧИКИ ====================

@dp.callback_query(F.data == "admin_stats")
async def callback_admin_stats(callback: CallbackQuery):
    """Обработчик статистики админа"""
    await callback.answer()
    
    if not db.is_admin(callback.from_user.id):
        await callback.message.answer("❌ Нет доступа")
        return
    
    stats = db.get_stats()
    
    stats_text = (
        "📊 **Подробная статистика**\n\n"
        f"• Всего пользователей: **{stats['total_users']}**\n"
        f"• Всего генераций: **{stats['total_generations']}**\n"
        f"• Активных сегодня: **{stats['active_today']}**\n\n"
        f"Среднее генераций на пользователя: **{stats['total_generations'] / max(stats['total_users'], 1):.1f}**"
    )
    
    await callback.message.edit_text(
        stats_text,
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )

@dp.callback_query(F.data == "admin_users")
async def callback_admin_users(callback: CallbackQuery, page: int = 0):
    """Обработчик списка пользователей"""
    await callback.answer()
    
    if not db.is_admin(callback.from_user.id):
        return
    
    users = db.get_all_users()
    users_per_page = 5
    
    total_pages = (len(users) + users_per_page - 1) // users_per_page
    page = min(page, max(0, total_pages - 1))
    
    start_idx = page * users_per_page
    end_idx = start_idx + users_per_page
    users_page = users[start_idx:end_idx]
    
    text = f"👥 **Список пользователей** (стр. {page + 1}/{total_pages})\n\n"
    
    for user in users_page:
        status = "⛔" if user['is_banned'] else "✅"
        admin = "👑" if user['is_admin'] else ""
        name = user['username'] or user['first_name'] or str(user['user_id'])
        text += f"{status}{admin} **{name}**\n"
        text += f"   🆔 `{user['user_id']}` | 🎨 {user['total_generations']} | 🕐 {user['last_active'][:16]}\n\n"
    
    # Создаем клавиатуру с пагинацией
    builder = InlineKeyboardBuilder()
    
    if page > 0:
        builder.add(InlineKeyboardButton(
            text="◀️ Назад",
            callback_data=f"users_page_{page - 1}"
        ))
    
    if page < total_pages - 1:
        builder.add(InlineKeyboardButton(
            text="Вперед ▶️",
            callback_data=f"users_page_{page + 1}"
        ))
    
    builder.add(InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="admin_panel"
    ))
    builder.adjust(2)
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data.startswith("users_page_"))
async def callback_users_page(callback: CallbackQuery):
    """Обработчик пагинации пользователей"""
    page = int(callback.data.replace("users_page_", ""))
    await callback_admin_users(callback, page)

@dp.callback_query(F.data == "admin_panel")
async def callback_admin_panel(callback: CallbackQuery):
    """Обработчик возврата в админ панель"""
    await callback.answer()
    
    if not db.is_admin(callback.from_user.id):
        return
    
    stats = db.get_stats()
    
    admin_text = (
        "👑 **Админ панель**\n\n"
        f"📊 **Общая статистика:**\n"
        f"• Всего пользователей: **{stats['total_users']}**\n"
        f"• Всего генераций: **{stats['total_generations']}**\n"
        f"• Активных сегодня: **{stats['active_today']}**\n\n"
        "Выберите действие:"
    )
    
    await callback.message.edit_text(
        admin_text,
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )

@dp.callback_query(F.data.startswith("ban_"))
async def callback_ban_user(callback: CallbackQuery):
    """Обработчик бана пользователя"""
    user_id = int(callback.data.replace("ban_", ""))
    
    if not db.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    if db.ban_user(user_id, callback.from_user.id):
        await callback.answer("✅ Пользователь забанен")
        
        # Обновляем сообщение
        await callback.message.edit_reply_markup(
            reply_markup=get_user_actions_keyboard(user_id)
        )
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                "⛔ Вы были заблокированы администратором."
            )
        except:
            pass
    else:
        await callback.answer("❌ Не удалось забанить")

@dp.callback_query(F.data.startswith("unban_"))
async def callback_unban_user(callback: CallbackQuery):
    """Обработчик разбана пользователя"""
    user_id = int(callback.data.replace("unban_", ""))
    
    if not db.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    if db.unban_user(user_id):
        await callback.answer("✅ Пользователь разбанен")
        
        # Обновляем сообщение
        await callback.message.edit_reply_markup(
            reply_markup=get_user_actions_keyboard(user_id)
        )
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                "✅ Вы были разблокированы администратором."
            )
        except:
            pass
    else:
        await callback.answer("❌ Не удалось разбанить")

# ==================== ЗАПУСК БОТА ====================

async def main():
    """Главная функция"""
    print("=" * 50)
    print("🚀 Telegram Image Generator Bot запущен!")
    print("=" * 50)
    print(f"🤖 Токен: {BOT_TOKEN[:10]}...{BOT_TOKEN[-10:] if len(BOT_TOKEN) > 20 else ''}")
    print(f"👑 Админ ID: {ADMIN_ID}")
    print(f"📊 Лимит генераций: {MAX_GENERATIONS_PER_DAY} в день")
    print("=" * 50)
    print("Команды бота:")
    print("  • /start - начать работу")
    print("  • /generate - сгенерировать изображение")
    print("  • /stats - моя статистика")
    print("  • /settings - настройки")
    print("  • /help - помощь")
    print("=" * 50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
