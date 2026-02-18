import telebot
from telebot import types
import json
import random
from datetime import datetime
import time

# Токен бота
TOKEN = '8195502253:AAEP86kffdNCDaVj2XKXupO1_wsocxl7_9U'
bot = telebot.TeleBot(TOKEN)

# Класс для управления игрой
class MonopolyGame:
    def __init__(self):
        self.games = {}  # Словарь для хранения активных игр
        self.players = {}  # Словарь для хранения игроков
        
    def create_game(self, chat_id, creator_id):
        """Создание новой игры"""
        game_id = f"{chat_id}_{int(time.time())}"
        self.games[game_id] = {
            'chat_id': chat_id,
            'creator': creator_id,
            'players': [],
            'status': 'waiting',  # waiting, playing, finished
            'current_turn': 0,
            'board': self.create_board(),
            'start_time': datetime.now()
        }
        return game_id
    
    def create_board(self):
        """Создание игровой доски"""
        return [
            {'name': 'Старт', 'type': 'start', 'price': 0},
            {'name': 'Улица Мира', 'type': 'property', 'price': 60, 'rent': 2, 'owner': None},
            {'name': 'Общественная казна', 'type': 'chance', 'price': 0},
            {'name': 'Невский проспект', 'type': 'property', 'price': 100, 'rent': 6, 'owner': None},
            {'name': 'Налог', 'type': 'tax', 'price': -200},
            {'name': 'Вокзал', 'type': 'railroad', 'price': 200, 'rent': 25, 'owner': None},
            {'name': 'Тверская улица', 'type': 'property', 'price': 140, 'rent': 10, 'owner': None},
            {'name': 'Шанс', 'type': 'chance', 'price': 0},
            {'name': 'Арбат', 'type': 'property', 'price': 180, 'rent': 14, 'owner': None},
            {'name': 'Тюрьма', 'type': 'jail', 'price': 0},
            {'name': 'Парк культуры', 'type': 'property', 'price': 220, 'rent': 18, 'owner': None},
            {'name': 'Электростанция', 'type': 'utility', 'price': 150, 'rent': 0, 'owner': None},
            {'name': 'Кузнецкий мост', 'type': 'property', 'price': 260, 'rent': 22, 'owner': None},
            {'name': 'Шанс', 'type': 'chance', 'price': 0},
            {'name': 'Красная площадь', 'type': 'property', 'price': 300, 'rent': 26, 'owner': None},
        ]
    
    def add_player(self, game_id, player_id, player_name):
        """Добавление игрока в игру"""
        if game_id in self.games:
            player_data = {
                'id': player_id,
                'name': player_name,
                'money': 1500,
                'position': 0,
                'properties': [],
                'in_jail': False,
                'jail_turns': 0
            }
            self.games[game_id]['players'].append(player_data)
            return True
        return False
    
    def start_game(self, game_id):
        """Начало игры"""
        if game_id in self.games and len(self.games[game_id]['players']) >= 2:
            self.games[game_id]['status'] = 'playing'
            return True
        return False
    
    def roll_dice(self):
        """Бросок кубиков"""
        return random.randint(1, 6), random.randint(1, 6)
    
    def move_player(self, game_id, player_index):
        """Перемещение игрока"""
        game = self.games[game_id]
        player = game['players'][player_index]
        
        dice1, dice2 = self.roll_dice()
        steps = dice1 + dice2
        
        old_position = player['position']
        new_position = (old_position + steps) % len(game['board'])
        player['position'] = new_position
        
        # Проход через старт
        if new_position < old_position:
            player['money'] += 200
            bot.send_message(game['chat_id'], f"{player['name']} прошел через Старт и получил 200💰")
        
        return dice1, dice2, new_position
    
    def handle_landing(self, game_id, player_index):
        """Обработка попадания на клетку"""
        game = self.games[game_id]
        player = game['players'][player_index]
        cell = game['board'][player['position']]
        
        if cell['type'] == 'property' or cell['type'] == 'railroad' or cell['type'] == 'utility':
            if cell['owner'] is None:
                return f"buy|{cell['name']}|{cell['price']}"
            elif cell['owner'] != player['id']:
                rent = cell['rent']
                player['money'] -= rent
                # Найти владельца и добавить ему деньги
                for p in game['players']:
                    if p['id'] == cell['owner']:
                        p['money'] += rent
                        break
                return f"pay|{cell['owner']}|{rent}"
        elif cell['type'] == 'tax':
            player['money'] += cell['price']  # price отрицательный для налогов
            return f"tax|{abs(cell['price'])}"
        elif cell['type'] == 'chance':
            return self.handle_chance(game_id, player_index)
        
        return "continue"
    
    def handle_chance(self, game_id, player_index):
        """Обработка клетки 'Шанс'"""
        game = self.games[game_id]
        player = game['players'][player_index]
        
        chances = [
            {"text": "Вы выиграли в лотерее! +200💰", "money": 200},
            {"text": "Штраф за превышение скорости -100💰", "money": -100},
            {"text": "Отправляйтесь в тюрьму", "jail": True},
            {"text": "Получите наследство +150💰", "money": 150},
            {"text": "Ремонт автомобиля -50💰", "money": -50},
            {"text": "Вы нашли клад! +300💰", "money": 300},
        ]
        
        chance = random.choice(chances)
        message = f"🎲 Шанс: {chance['text']}"
        
        if 'money' in chance:
            player['money'] += chance['money']
        elif 'jail' in chance:
            player['in_jail'] = True
            player['position'] = 9  # Позиция тюрьмы
            
        return f"chance|{message}"
    
    def buy_property(self, game_id, player_index):
        """Покупка собственности"""
        game = self.games[game_id]
        player = game['players'][player_index]
        cell = game['board'][player['position']]
        
        if player['money'] >= cell['price']:
            player['money'] -= cell['price']
            cell['owner'] = player['id']
            player['properties'].append(player['position'])
            return True
        return False

# Создаем экземпляр игры
monopoly = MonopolyGame()

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('🎮 Новая игра'))
    markup.add(types.KeyboardButton('📊 Статистика'))
    markup.add(types.KeyboardButton('ℹ️ Помощь'))
    
    bot.send_message(
        message.chat.id,
        "🎲 Добро пожаловать в игру Монополия!\n\n"
        "Здесь вы можете сыграть в экономическую стратегию с друзьями.\n"
        "Нажмите 'Новая игра' для создания игры или 'Помощь' для получения информации.",
        reply_markup=markup
    )

# Обработчик команды /help
@bot.message_handler(commands=['help'])
def help_command(message):
    bot.send_message(
        message.chat.id,
        "📚 Правила игры Монополия:\n\n"
        "🎯 Цель: стать самым богатым игроком, покупая недвижимость и собирая арендную плату\n\n"
        "💰 Начальный капитал: 1500$\n"
        "🎲 Игроки по очереди бросают кубики\n"
        "🏠 Можно покупать свободные участки\n"
        "💵 За попадание на чужую собственность нужно платить аренду\n"
        "⭐ За прохождение круга дается 200$\n"
        "🏛 В тюрьме игрок пропускает ход\n\n"
        "Команды:\n"
        "/start - Начать игру\n"
        "/join - Присоединиться к игре\n"
        "/status - Текущий статус игры\n"
        "/help - Правила игры"
    )

# Обработчик текстовых сообщений
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if message.text == '🎮 Новая игра':
        create_game(message)
    elif message.text == '📊 Статистика':
        show_stats(message)
    elif message.text == 'ℹ️ Помощь':
        help_command(message)

def create_game(message):
    """Создание новой игры"""
    game_id = monopoly.create_game(message.chat.id, message.from_user.id)
    monopoly.add_player(game_id, message.from_user.id, message.from_user.first_name)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Присоединиться", callback_data=f"join_{game_id}"))
    markup.add(types.InlineKeyboardButton("Начать игру", callback_data=f"start_game_{game_id}"))
    
    bot.send_message(
        message.chat.id,
        f"🎮 Создана новая игра!\n"
        f"Создатель: {message.from_user.first_name}\n"
        f"ID игры: {game_id}\n\n"
        f"Ожидаем игроков... (минимум 2)",
        reply_markup=markup
    )

def show_stats(message):
    """Показать статистику игрока"""
    # Здесь можно добавить статистику игрока
    bot.send_message(
        message.chat.id,
        "📊 Ваша статистика пока пуста.\n"
        "Сыграйте несколько игр, чтобы увидеть результаты!"
    )

# Обработчик callback запросов
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data.startswith('join_'):
        game_id = call.data.replace('join_', '')
        if game_id in monopoly.games:
            game = monopoly.games[game_id]
            if game['status'] == 'waiting':
                # Проверяем, не присоединился ли уже игрок
                if not any(p['id'] == call.from_user.id for p in game['players']):
                    monopoly.add_player(game_id, call.from_user.id, call.from_user.first_name)
                    bot.answer_callback_query(call.id, "Вы присоединились к игре!")
                    
                    # Обновляем сообщение с игроками
                    players_list = "\n".join([f"👤 {p['name']}" for p in game['players']])
                    bot.edit_message_text(
                        f"🎮 Игра в процессе создания!\n"
                        f"Создатель: {game['creator']}\n"
                        f"ID игры: {game_id}\n\n"
                        f"Игроки:\n{players_list}\n\n"
                        f"Ожидаем игроков... ({len(game['players'])}/∞)",
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id
                    )
                    
                    # Если игроков уже достаточно, предлагаем начать
                    if len(game['players']) >= 2:
                        markup = types.InlineKeyboardMarkup()
                        markup.add(types.InlineKeyboardButton("Начать игру!", callback_data=f"start_game_{game_id}"))
                        bot.send_message(
                            game['chat_id'],
                            "✅ Достаточно игроков для начала игры!\n"
                            "Нажмите кнопку ниже, чтобы начать.",
                            reply_markup=markup
                        )
                else:
                    bot.answer_callback_query(call.id, "Вы уже в игре!")
            else:
                bot.answer_callback_query(call.id, "Игра уже началась!")
    
    elif call.data.startswith('start_game_'):
        game_id = call.data.replace('start_game_', '')
        if game_id in monopoly.games:
            game = monopoly.games[game_id]
            if call.from_user.id == game['creator']:
                if len(game['players']) >= 2:
                    if monopoly.start_game(game_id):
                        bot.answer_callback_query(call.id, "Игра начинается!")
                        start_playing(call.message.chat.id, game_id)
                    else:
                        bot.answer_callback_query(call.id, "Не удалось начать игру")
                else:
                    bot.answer_callback_query(call.id, "Нужно минимум 2 игрока!")
            else:
                bot.answer_callback_query(call.id, "Только создатель может начать игру!")

def start_playing(chat_id, game_id):
    """Начало игрового процесса"""
    game = monopoly.games[game_id]
    
    # Отправляем приветственное сообщение
    players_list = "\n".join([f"👤 {p['name']} (${p['money']})" for p in game['players']])
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎲 Бросить кубики", callback_data=f"turn_{game_id}_{game['current_turn']}"))
    
    bot.send_message(
        chat_id,
        f"🎲 ИГРА НАЧИНАЕТСЯ!\n\n"
        f"Игроки:\n{players_list}\n\n"
        f"Первый ход: {game['players'][0]['name']}\n"
        f"Нажмите кнопку, чтобы бросить кубики!",
        reply_markup=markup
    )

# Запуск бота
if __name__ == '__main__':
    print("Бот запущен...")
    bot.infinity_polling()
