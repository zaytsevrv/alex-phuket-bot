import csv
import logging
import re
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
)
import sqlite3
from datetime import datetime
import asyncio

# === АНАЛИТИКА ===
from analytics.logger import logger
from config import ADMIN_ID, BOT_STAGES, QUESTION_TYPES, ERROR_TYPES
import json
# === КОНЕЦ ИМПОРТОВ АНАЛИТИКИ ===

# === ИМПОРТ ФУНКЦИЙ ПАРСЕРА ===
from parser_functions import parse_user_response, age_to_months, format_age_months
# === КОНЕЦ ИМПОРТОВ ПАРСЕРА ===

# === ИМПОРТ OPENAI ДЛЯ DEEPSEEK ===
import openai
# === КОНЕЦ ИМПОРТА OPENAI ===

# === НАЧАЛО БЕЗОПАСНОЙ ЗАГРУЗКИ ТОКЕНА ===
import os
from dotenv import load_dotenv

# Пробуем загрузить переменные из файла .env
load_dotenv()

# Пытаемся получить токен из безопасного места
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Если токена в .env нет — программа упадет с понятной ошибкой ДО запуска бота,
# а не станет использовать старый зашитый токен.
if TELEGRAM_BOT_TOKEN is None:
    raise ValueError(
        "❌ ТОКЕН БОТА НЕ НАЙДЕН!\n"
        "1. Убедитесь, что в папке с bot.py есть файл .env\n"
        "2. В файле .env должна быть строка: TELEGRAM_BOT_TOKEN=ваш_токен_здесь\n"
        "3. НИКОГДА не загружайте файл .env на GitHub!"
    )

# Загружаем API ключ для DeepSeek
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
if DEEPSEEK_API_KEY is None:
    print("⚠️ DEEPSEEK_API_KEY не найден. DeepSeek интеграция будет отключена.")
    DEEPSEEK_API_KEY = None

# === КОНЕЦ БЛОКА БЕЗОПАСНОЙ ЗАГРУЗКИ ТОКЕНА ===
# ==================== БАЗА ДАННЫХ ====================
DB_FILE = "bot_statistics.db"

# ==================== НАСТРОЙКИ ====================
# Замените на ваш токен!
CSV_FILE = "Price22.12.2025.csv"

# Состояния диалога (шаги)
CATEGORY, QUALIFICATION, CONFIRMATION, TOUR_DETAILS, QUESTION, BOOKING, BOOKING_HOTEL = range(7)

# Включим логирование для отладки
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# ==================== ЗАГРУЗКА ДАННЫХ ====================
def load_tours():
    """Загружает экскурсии из CSV файла"""
    tours = []
    try:
        with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:  # utf-8-sig для обработки BOM
            # --- ДОБАВЛЯЮ ОТЛАДКУ ПОЛЕЙ ---
            sample = f.read(500)
            print("🔍 Первые 500 символов CSV:")
            print(sample)
            print("\n" + "="*50 + "\n")
            
            f.seek(0)  # Возвращаемся в начало
            reader = csv.DictReader(f, delimiter=';')
            
            # Выводим названия полей для проверки
            if reader.fieldnames:
                print("📋 Обнаруженные поля в CSV:")
                for i, field in enumerate(reader.fieldnames):
                    print(f"   {i+1:2d}. '{field}'")
            
            for row in reader:
                # Очищаем значения от лишних пробелов
                clean_row = {key.strip(): (value.strip() if value else "") for key, value in row.items()}
                tours.append(clean_row)
                
                # Выводим первую запись для проверки структуры
                if len(tours) == 1:
                    print("\n📝 Пример первой записи (первые 5 полей):")
                    for i, (key, value) in enumerate(clean_row.items()):
                        if i < 5 and value:
                            print(f"   '{key}': '{value[:50]}...'")
            
            print(f"\n✅ Загружено {len(tours)} экскурсий из CSV")
            return tours
    except Exception as e:
        print(f"❌ Ошибка загрузки CSV: {e}")
        import traceback
        traceback.print_exc()
        return []

# Загружаем данные при старте
TOURS = load_tours()

# ==================== БАЗА ДАННЫХ ====================
def init_database():
    """Инициализация базы данных для сбора статистики"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Таблица действий
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action_type TEXT,
            action_details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')
        
        # Таблица диалогов
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT,
            adults INTEGER DEFAULT 0,
            children_count INTEGER DEFAULT 0,
            children_ages TEXT,
            pregnant BOOLEAN,
            priorities TEXT,
            health_issues TEXT,
            selected_tour_id INTEGER,
            conversation_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            conversation_end TIMESTAMP,
            successful BOOLEAN DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')
        
        conn.commit()
        conn.close()
        print(f"✅ База данных {DB_FILE} создана")
    except Exception as e:
        print(f"⚠️ Предупреждение БД: {e}")

# Инициализируем БД
init_database()

def log_user_action(user_id, action_type, action_details=""):
    """Логирование действий пользователя"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, last_seen)
        VALUES (?, CURRENT_TIMESTAMP)
        ''', (user_id,))
        
        cursor.execute('''
        INSERT INTO actions (user_id, action_type, action_details)
        VALUES (?, ?, ?)
        ''', (user_id, action_type, str(action_details)))
        
        conn.commit()
    except Exception as e:
        print(f"❌ Ошибка логирования: {e}")
    finally:
        if conn:
            conn.close()

def start_conversation_log(user_id, category):
    """Начать запись диалога"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO conversations (user_id, category, conversation_start)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, category))
        
        conv_id = cursor.lastrowid
        conn.commit()
        return conv_id
    except Exception as e:
        print(f"❌ Ошибка начала диалога: {e}")
        return None
    finally:
        if conn:
            conn.close()

def update_conversation_log(conv_id, **kwargs):
    """Обновить запись диалога"""
    if not conv_id:
        return
    
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        updates = []
        values = []
        
        for key, value in kwargs.items():
            updates.append(f"{key} = ?")
            values.append(value)
        
        values.append(conv_id)
        
        query = f'''
        UPDATE conversations 
        SET {', '.join(updates)}
        WHERE id = ?
        '''
        
        cursor.execute(query, values)
        conn.commit()
    except Exception as e:
        print(f"❌ Ошибка обновления диалога: {e}")
    finally:
        if conn:
            conn.close()

# ==================== КАТЕГОРИИ ====================
# Берем уникальные категории из CSV
def get_categories():
    categories = set()
    for tour in TOURS:
        category = tour.get("Для информации", "").strip()
        if category:
            categories.add(category)
    return sorted(list(categories))

def is_likely_question(text):
    """
    Определяет, является ли текст вопросом, а не попыткой выбрать категорию.
    Возвращает True если это похоже на вопрос.
    """
    text_lower = text.lower().strip()
    
    # Признаки вопроса
    question_markers = [
        '?',  # Вопросительный знак
        'где', 'куда', 'что', 'как', 'почему', 'когда', 'какой', 'какая',
        'помог', 'совет', 'рекомендуешь', 'подскажи', 'расскажи',
        'привет', 'привет!', 'привет,', 'привет)', 'привет :',
        'привет)', 'привет!', 'привет,', 'привет)', 'привет :',
        'хи', 'хей', 'эй', 'слушай', 'слушайте', 'давайте', 'давай',
        'вы можете', 'ты можешь', 'можно', 'есть ли', 'есть',
        'какие', 'сколько', 'во сколько', 'по сколько', 'цена',
        'стоит', 'дорого', 'дешево', 'бюджет', 'деньги',
        'симилан', 'пхи пхи', 'краби', 'пангнга', 'джамс бонд',
        'вопрос', 'интересует', 'узнать', 'расскажи про', 'расскажите про'
    ]
    
    # Если содержит маркеры вопроса - это вопрос
    for marker in question_markers:
        if marker in text_lower:
            return True
    
    # Если более 5 слов - скорее всего вопрос или предложение, а не команда
    words = text_lower.split()
    if len(words) >= 5:
        return True
    
    # Если много пробелов и слова не совпадают с категориями - вопрос
    if ' ' in text_lower:
        # Проверяем, начинается ли с маленькой буквы (признак естественной речи)
        if text[0].islower() and len(text) > 15:
            return True
    
    return False

def format_deepseek_answer(text):
    """
    Красиво форматирует ответ DeepSeek для отправки в Telegram.
    Добавляет разбиение на абзацы и улучшает визуальное восприятие.
    """
    if not text:
        return text
    
    # Заменяем двойные точки на иконки для лучшего формата
    text = text.replace('•', '▪️')
    
    # Если текст содержит точки - разбиваем на абзацы (каждое предложение на новую строку)
    # но сохраняем список буллетов
    sentences = text.split('. ')
    if len(sentences) > 2:
        # Есть несколько предложений - разделяем их
        formatted_lines = []
        for i, sentence in enumerate(sentences):
            sentence = sentence.strip()
            if not sentence:
                continue
            # Добавляем точку обратно если её нет
            if not sentence.endswith('.'):
                sentence += '.'
            formatted_lines.append(sentence)
        
        # Группируем по 2 предложения в абзац для лучшего восприятия
        text = '\n\n'.join(formatted_lines)
    
    # Дополняем эмодзи в нужных местах для визуального интереса
    emoji_replacements = {
        'Пхи-Пхи': '🏝️ Пхи-Пхи',
        'Симилан': '🌊 Симилан',
        'тур': '🎫 тур',
        'цена': '💰 цена',
        'группа': '👥 группа',
        'кораллы': '🪸 кораллы',
        'дайвинг': '🤿 дайвинг',
        'снорклинг': '🏊 снорклинг',
        'пляж': '🏖️ пляж',
        'рыба': '🐠 рыба',
        'Юг': '⛵ Юг',
        'Север': '🧭 Север',
    }
    
    # Очень осторожно добавляем эмодзи чтобы не переделать всё
    for key, emoji in emoji_replacements.items():
        # Только если этот emoji ещё не добавлен
        if key in text and emoji not in text:
            text = text.replace(key, emoji, 1)  # Только первое вхождение
    
    return text

def search_tours_by_keywords(query):
    """
    Ищет туры по ключевому слову/фразе во всех полях прайса.
    Проверяет: название, ключевые слова, описание, теги.
    Возвращает список кортежей (тур, категория, релевантность)
    """
    query_lower = query.lower().strip()
    if not query_lower:
        return []
    
    results = []
    
    for tour in TOURS:
        relevance = 0
        
        # 1. Проверяем название (самый высокий приоритет)
        tour_name = tour.get('Название', '').lower()
        if query_lower in tour_name:
            relevance += 100
        
        # 2. Проверяем ключевые слова
        keywords = tour.get('Ключевые слова', '')
        if keywords:
            keywords_lower = str(keywords).lower()
            if query_lower in keywords_lower:
                relevance += 50
            # Ищем по отдельным словам
            query_words = query_lower.split()
            for word in query_words:
                if word in keywords_lower:
                    relevance += 10
        
        # 3. Проверяем описание витрины
        description = tour.get('Описание (Витрина)', '')
        if description:
            description_lower = str(description).lower()
            if query_lower in description_lower:
                relevance += 30
        
        # 4. Проверяем честный обзор
        review = tour.get('Честный обзор', '')
        if review:
            review_lower = str(review).lower()
            if query_lower in review_lower:
                relevance += 20
        
        # Если нашли совпадение - добавляем в результаты
        if relevance > 0:
            category = tour.get('Для информации', 'Неизвестная категория')
            results.append((tour, category, relevance))
    
    # Сортируем по релевантности (выше релевантность = выше в списке)
    results.sort(key=lambda x: x[2], reverse=True)
    
    return results

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ВИЗУАЛА ===

async def send_message_with_effect(update, text, reply_markup=None, parse_mode='Markdown', use_effect=True):
    """Отправляет сообщение с эффектом салюта"""
    try:
        if use_effect:
            # Отправляем с эффектом салюта
            await update.message.reply_text(
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                message_effect_id="5104841245755180586"  # ID салюта
            )
        else:
            # Обычная отправка без эффекта
            await update.message.reply_text(
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
    except Exception as e:
        # Если эффект не поддерживается - отправляем без него
        print(f"⚠️ Салют не поддерживается, отправляю обычное сообщение: {e}")
        await update.message.reply_text(
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )

# Клавиатура с категориями
def make_category_keyboard():
    categories = get_categories()
    # Создаем кнопки по 3 в ряд для оптимизации места на экране
    keyboard = []
    for i in range(0, len(categories), 3):
        row = categories[i:i+3]
        keyboard.append(row)
    # Добавляем кнопку "Новый поиск" в конце
    keyboard.append(["🔄 Новый поиск"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

# ==================== ФУНКЦИЯ ДЛЯ КОНВЕРТАЦИИ ВОЗРАСТА ====================
def age_to_months(age_str):
    """
    Конвертирует текст возраста в месяцы для точной проверки ограничений.
    """
    if not age_str:
        return 0
    
    age_str = str(age_str).lower().strip()
    total_months = 0
    
    # === НОВЫЙ КОД: Обработка комбинированных возрастов ===
    # Паттерн для "2 года и 7 месяцев", "1 год 3 месяца"
    combined_pattern = r'(\d+)\s*(?:лет|год[а]?|г\.?|л\.?)\s*(?:и\s*)?(\d+)?\s*(?:месяц[а-я]*|мес\.?|м\.?)?'
    match = re.search(combined_pattern, age_str)
    
    if match:
        years = int(match.group(1)) if match.group(1) else 0
        months = int(match.group(2)) if match.group(2) else 0
        total_months = years * 12 + months
        return total_months
    
    # Старая логика для простых форматов
    # Ищем годы
    year_match = re.search(r'(\d+)\s*(?:лет|год[а]?|г\.?|л\.?)', age_str)
    if year_match:
        years = int(year_match.group(1))
        total_months += years * 12
    
    # Ищем месяцы
    month_match = re.search(r'(\d+)\s*(?:месяц[а-я]*|мес\.?|м\.?)', age_str)
    if month_match:
        months = int(month_match.group(1))
        total_months += months
    
    # Если просто число без указания единиц
    if total_months == 0 and age_str.isdigit():
        total_months = int(age_str) * 12
    
    return total_months

def format_age_months(months):
    """
    Форматирует возраст в месяцах в читаемый вид с округлением ВНИЗ.
    
    Правила:
    - До 12 месяцев: показываем месяцы (9 мес.)
    - От 12 месяцев: округляем ВНИЗ до целых лет
    - 1 год и 11 месяцев → 1 год
    - 2 года и 7 месяцев → 2 года
    """
    if months < 12:
        # Меньше года - показываем месяцы
        return f"{months} мес."
    
    # Больше или равно году - округляем ВНИЗ до целых лет
    years = months // 12  # Целочисленное деление - округление вниз
    
    if years == 1:
        return "1 год"
    elif 2 <= years <= 4:
        return f"{years} года"
    else:
        return f"{years} лет"

# ==================== ФУНКЦИИ ДЛЯ ПОШАГОВОГО УТОЧНЕНИЯ ====================

def save_partial_data(context, new_data):
    """Сохраняет частичные данные пользователя"""
    if 'user_data' not in context.user_data:
        context.user_data['user_data'] = {
            'adults': 0,
            'children': [],        # возрасты в месяцах
            'children_original': [], # оригинальный текст возраста
            'pregnant': None,      # None = не указано
            'priorities': [],
            'health_issues': [],
            'raw_text': ''
        }
    
    user_data = context.user_data['user_data']
    
    # Объединяем raw_text
    if 'raw_text' in new_data and new_data['raw_text']:
        user_data['raw_text'] += " " + new_data['raw_text']
    
    # Обновляем взрослых (только если указано явно)
    if 'adults' in new_data and new_data['adults'] > 0:
        user_data['adults'] = new_data['adults']
    
    # Обновляем детей
    if 'children' in new_data and new_data['children']:
        for age, original in zip(new_data['children'], new_data['children_original']):
            if age not in user_data['children']:
                user_data['children'].append(age)
                user_data['children_original'].append(original)
    
    # Обновляем беременность (только если явно указано)
    if 'pregnant' in new_data and new_data['pregnant'] is not None:
        user_data['pregnant'] = new_data['pregnant']
    
    # Обновляем приоритеты
    if 'priorities' in new_data:
        for priority in new_data['priorities']:
            if priority not in user_data['priorities']:
                user_data['priorities'].append(priority)
    
    # Обновляем проблемы со здоровьем
    if 'health_issues' in new_data:
        for issue in new_data['health_issues']:
            if issue not in user_data['health_issues']:
                user_data['health_issues'].append(issue)

def check_missing_points(user_data):
    """Проверяет, какие данные отсутствуют"""
    missing_points = []
    
    # Проверяем взрослых
    if user_data['adults'] == 0:
        missing_points.append("количество взрослых")
    
    # Проверяем беременность
    if user_data['pregnant'] is None:
        missing_points.append("беременность (да/нет)")
    
    # Проверяем информацию о детях
    raw_text_lower = user_data['raw_text'].lower() if user_data['raw_text'] else ""
    child_keywords = ['ребен', 'дет', 'малыш', 'младш', 'сын', 'доч']
    
    if any(keyword in raw_text_lower for keyword in child_keywords):
        if not user_data['children']:
            # Если упомянули детей, но возрастов нет
            missing_points.append("информация о детях")
    
    return missing_points

async def ask_for_clarification(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data, missing_points):
    """Спрашивает уточнение для непонятых данных"""
    
    response = "✅ *Часть информации я понял:*\n\n"
    
    # Что понял
    understood = []
    if user_data['adults'] > 0:
        understood.append(f"👨‍👩‍👧‍👦 Взрослых: {user_data['adults']}")
    if user_data['children']:
        children_count = len(user_data['children'])
        understood.append(f"👶 Дети: {children_count} детей")
    if user_data['pregnant'] is not None:
        understood.append(f"🤰 Беременность: {'Да' if user_data['pregnant'] else 'Нет'}")
    
    if understood:
        response += "\n".join(understood) + "\n\n"
    else:
        response += "Пока ничего не понял 😅\n\n"
    
    # Что нужно уточнить (спрашиваем по одному)
    if "количество взрослых" in missing_points:
        response += "❓ *Сколько взрослых в группе?*\n"
        context.user_data['next_question'] = 'adults'
    
    elif "беременность (да/нет)" in missing_points:
        response += "❓ *Есть ли беременные в группе? (Да/Нет)*\n"
        context.user_data['next_question'] = 'pregnant'
    
    elif "информация о детях" in missing_points:
        response += "❓ *Есть ли дети? Если да, укажите возраст каждого.*\n"
        context.user_data['next_question'] = 'children'
    
    response += "\n*Пожалуйста, ответьте на вопрос выше.*"
    
    await update.message.reply_text(
        response,
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )

async def show_final_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data):
    """Показывает финальное подтверждение когда все данные собраны"""
    response = "✅ *Отлично! Теперь у меня вся информация!*\n\n"
    
    response += f"👨‍👩‍👧‍👦 *Взрослых:* {user_data['adults']}\n"
    
    if user_data['children']:
        children_count = len(user_data['children'])
        age_texts = []
        
        for age_months in user_data['children']:
            if age_months > 0:  # Пропускаем маркеры (0)
                age_texts.append(format_age_months(age_months))
        
        # Проверяем, есть ли реальные возрасты (не только маркеры)
        if age_texts:
            if children_count == 1:
                response += f"👶 *Дети:* 1 ребенок ({', '.join(age_texts)})\n"
            elif children_count in [2, 3, 4]:
                response += f"👶 *Дети:* {children_count} ребенка ({', '.join(age_texts)})\n"
            else:
                response += f"👶 *Дети:* {children_count} детей ({', '.join(age_texts)})\n"
        else:
            # Только маркеры количества (0) - возрастов нет
            response += f"👶 *Дети:* {children_count} детей (возраст не указан)\n"
    else:
        response += "👶 *Дети:* нет\n"
    
    response += f"🤰 *Беременность:* {'Да ✨' if user_data.get('pregnant') else 'Нет'}\n"
    
    if user_data['priorities']:
        response += f"🎯 *Важные моменты:* {', '.join(user_data['priorities'])}\n"
    
    if user_data['health_issues']:
        response += f"🏥 *Учитываем здоровье:* {', '.join(user_data['health_issues'])}\n"
    
    response += "\n✅ *Всё верно или нужно что-то исправить?*"
    
    keyboard = [["✅ Да, всё верно", "✏️ Нет, исправить"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        response,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

def get_smart_recommendations(user_data, current_category):
    """Возвращает умные рекомендации в стиле Алекса на основе ограничений пользователя"""
    
    is_pregnant = user_data.get('pregnant', False)
    children_ages = user_data.get('children', [])
    has_young_children = any(age < 12 for age in children_ages)  # до 1 года
    has_toddlers = any(12 <= age < 48 for age in children_ages)  # 1-4 года
    has_older_children = any(age >= 48 for age in children_ages)  # от 4 лет
    
    recommendations = []
    alex_style = "\n\n🎯 **Алекс рекомендует:**\n"
    
    # Проверяем ограничения
    if is_pregnant:
        alex_style += "✨ *Для беременных* — выбирайте только проверенные безопасные варианты!\n"
        
        if "Море" in current_category or "Яхты" in current_category:
            recommendations.append("🌊 *Море* — увы, запрещены все морские туры")
            recommendations.append("🏞️ *Суша (обзорные)* — идеально! Аватар, смотровые, горячие источники")
            recommendations.append("🐘 *Суша (семейные)* — слоны, аквапарки, дельфинарий")
            recommendations.append("🎭 *Вечерние шоу* — Сиам Нирамит, кабаре")
        
        elif "Рыбалка" in current_category:
            recommendations.append("🎣 *Рыбалка* — только озерная (биг гейм нельзя!)")
            recommendations.append("🏞️ *Суша* — отличная альтернатива")
    
    if has_young_children:  # Дети до 1 года
        alex_style += "👶 *С малышами до года* — нужен особый подход и безопасность!\n"
        
        if "Море" in current_category:
            recommendations.append("🌊 *Море* — малышам запрещены все морские программы")
            recommendations.append("🐘 *Суша (семейные)* — вот где раздолье! Слоны, кормление птиц, океанариум")
            recommendations.append("🏞️ *Суша (обзорные)* — Аватар, джипы, Као Лак сафари")
            recommendations.append("👶 *Специально для малышей:* Кормление слонов, Парк птиц, Океанариум Aquaria")
    
    if has_toddlers:  # Дети 1-4 года
        alex_style += "🧒 *С детками 1-4 года* — много интересных вариантов!\n"
        
        if "Море" in current_category:
            recommendations.append("🌊 *Море* — можно, но будтьте внимательны, изучите подробно всю информацию о выбранной экскурсии")
            recommendations.append("🛥️ *Яхты* — только частные аренды с условием безопасности")
            recommendations.append("🐘 *Суша (семейные)* — идеально подходит!")
    
    # Если есть рекомендации - оформляем в стиле Алекса
    if recommendations:
        # Убираем дубликаты
        unique_recs = []
        for rec in recommendations:
            if rec not in unique_recs:
                unique_recs.append(rec)
        
        # Форматируем в стиле Алекса
        alex_style += "\n💡 *Куда можно сходить вместо этого:*\n"
        for rec in unique_recs:
            alex_style += f"• {rec}\n"
        
        # Добавляем финальную фразу в стиле Алекса
        alex_style += "\n_Давайте подберём что-то идеальное именно для вас! Просто выберите другую категорию или уточните пожелания._ ✨"
        
        return alex_style
    
    return ""  # Если рекомендаций нет

async def handle_correction(update: Update, context: ContextTypes.DEFAULT_TYPE, correction_text):
    """Обработка исправлений от пользователя"""
    user_data = context.user_data.get('user_data', {})
    
    # Парсим то, что написал пользователь
    parsed_data, _ = parse_user_response(correction_text)
    
    # === ОСОБАЯ ЛОГИКА ДЛЯ ИСПРАВЛЕНИЯ ДЕТЕЙ ===
    # Если пользователь указал количество детей, но не указал возрасты
    # И у нас уже были возрасты - распределяем возрасты
    if parsed_data['children'] and len(parsed_data['children']) == 1 and parsed_data['children'][0] == 0:
        # Пользователь указал только количество (маркер 0)
        # Например: "2 ребенка" → children: [0], children_original: ['количество']
        requested_count = len(parsed_data['children_original'])
        
        # Если у нас уже были возрасты
        if user_data['children'] and any(age > 0 for age in user_data['children']):
            existing_ages = [age for age in user_data['children'] if age > 0]
            existing_originals = []
            
            # Собираем оригинальные тексты возрастов
            for i, age in enumerate(user_data['children']):
                if age > 0 and i < len(user_data['children_original']):
                    existing_originals.append(user_data['children_original'][i])
            
            # Если запросили больше детей чем есть возрастов
            if requested_count > len(existing_ages):
                # Добавляем маркеры для недостающих детей
                for _ in range(requested_count - len(existing_ages)):
                    existing_ages.append(0)
                    existing_originals.append('возраст не указан')
            
            # Обновляем данные
            parsed_data['children'] = existing_ages[:requested_count]
            parsed_data['children_original'] = existing_originals[:requested_count]
    
    # Если после исправления у нас есть дети с маркерами (0)
    # Нужно уточнить возраст
    if parsed_data['children'] and 0 in parsed_data['children']:
        # Считаем сколько детей без возраста
        children_without_age = parsed_data['children'].count(0)
        
        if children_without_age > 0:
            response = f"✅ Запомнил: {len(parsed_data['children'])} детей\n\n"
            response += f"❓ *Уточните возраст {children_without_age} ребенка:*\n"
            
            if children_without_age == 1:
                response += "Напишите возраст ребенка (например: 3 года, 8 месяцев)\n"
            else:
                response += f"Напишите возраст каждого из {children_without_age} детей\n"
                response += "Пример: '5 лет и 3 года' или '8 месяцев и 2 года'\n"
            
            # Сохраняем временные данные
            save_partial_data(context, parsed_data)
            
            # Устанавливаем вопрос про детей
            context.user_data['next_question'] = 'children'
            
            await update.message.reply_text(
                response,
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardRemove()
            )
            return CONFIRMATION
    
    # Сохраняем исправления
    save_partial_data(context, parsed_data)
    
    # Получаем обновлённые данные
    current_data = context.user_data['user_data']
    
    # Проверяем, всё ли теперь поняли
    current_missing = check_missing_points(current_data)
    
    if not current_missing:
        # Всё поняли - показываем финальное подтверждение
        await show_final_confirmation(update, context, current_data)
    else:
        # Ещё что-то не поняли - уточняем
        await ask_for_clarification(update, context, current_data, current_missing)
    
    return CONFIRMATION

# ==================== ФИЛЬТРАЦИЯ ЭКСКУРСИЙ ПО БЕЗОПАСНОСТИ ====================
def filter_tours_by_safety(tours, user_data):
    """
    СТРОГАЯ фильтрация экскурсий по тегам безопасности из CSV.
    Основывается ТОЛЬКО на столбце "Теги (Безопасность)".
    """
    filtered_tours = []
    
    is_pregnant = user_data.get('pregnant', False)
    children_ages = user_data.get('children', [])  # возрасты в месяцах
    health_issues = user_data.get('health_issues', [])
    
    for tour in tours:
        is_safe = True
        tags = tour.get("Теги (Безопасность)", "").lower()
        
        # === 1. ПРОВЕРКА ДЛЯ БЕРЕМЕННЫХ ===
        if is_pregnant:
            if "#нельзя_беременным" in tags:
                is_safe = False
            elif "#можно_беременным" not in tags and "#можно_всем" not in tags:
                # Если нет явного разрешения для беременных - по умолчанию нельзя
                is_safe = False
        
        # === 2. ПРОВЕРКА ВОЗРАСТА ДЕТЕЙ ===
        if children_ages:
            # Проверяем каждого ребенка на соответствие возрастным ограничениям
            for age_months in children_ages:
                child_safe = True
                
                # Если ребенок до 1 года (12 месяцев)
                if age_months < 12:
                    if "#дети_от_1_года" in tags or "#от_18_лет" in tags or "#дети_от_2_лет" in tags or \
                       "#дети_от_3_лет" in tags or "#дети_от_4_лет" in tags or "#дети_от_7_лет" in tags or \
                       "#дети_от_12_лет" in tags:
                        child_safe = False
                    elif "#можно_детям" not in tags and "#можно_всем" not in tags:
                        # По умолчанию - если нет явного разрешения для детей
                        child_safe = False
                
                # Проверка по конкретным возрастным ограничениям
                elif 12 <= age_months < 24:  # 1-2 года
                    if "#дети_от_2_лет" in tags or "#дети_от_3_лет" in tags or \
                       "#дети_от_4_лет" in tags or "#дети_от_7_лет" in tags or \
                       "#дети_от_12_лет" in tags or "#от_18_лет" in tags:
                        child_safe = False
                
                elif 24 <= age_months < 36:  # 2-3 года
                    if "#дети_от_3_лет" in tags or "#дети_от_4_лет" in tags or \
                       "#дети_от_7_лет" in tags or "#дети_от_12_лет" in tags or \
                       "#от_18_лет" in tags:
                        child_safe = False
                
                elif 36 <= age_months < 48:  # 3-4 года
                    if "#дети_от_4_лет" in tags or "#дети_от_7_лет" in tags or \
                       "#дети_от_12_лет" in tags or "#от_18_лет" in tags:
                        child_safe = False
                
                elif 48 <= age_months < 84:  # 4-7 лет
                    if "#дети_от_7_лет" in tags or "#дети_от_12_лет" in tags or \
                       "#от_18_лет" in tags:
                        child_safe = False
                
                elif 84 <= age_months < 144:  # 7-12 лет
                    if "#дети_от_12_лет" in tags or "#от_18_лет" in tags:
                        child_safe = False
                
                elif 144 <= age_months < 216:  # 12-18 лет
                    if "#от_18_лет" in tags:
                        child_safe = False
                
                # Если хотя бы один ребенок не подходит - вся экскурсия не подходит
                if not child_safe:
                    is_safe = False
                    break
        
        # === 3. ПРОВЕРКА ПРОБЛЕМ СО ЗДОРОВЬЕМ ===
        if health_issues:
            # Проблемы со спиной - исключаем теги с нагрузкой
            if 'спина' in health_issues:
                if "#проблемы_спины" in tags or "#нагрузка" in tags:
                    is_safe = False
            
            # Укачивание - исключаем морские/скоростные туры
            if 'укачивание' in health_issues:
                if "#скорость" in tags or "#трясет" in tags or "#волны" in tags:
                    is_safe = False
        
        # === 4. ЕСЛИ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ - ДОБАВЛЯЕМ ===
        if is_safe:
            filtered_tours.append(tour)
    
    return filtered_tours

# ==================== РАНЖИРОВАНИЕ ЭКСКУРСИЙ ПО ПРИОРИТЕТАМ ====================
def rank_tours_by_hits_and_priorities(tours, user_data):
    """
    ЖЕСТКАЯ приоритизация: сначала ХИТы, потом остальные.
    Разделяет туры на 3 группы:
    1. ХИТы (ранжированные по приоритетам пользователя)
    2. Рекомендуемые (отфильтрованные по приоритетам)
    3. Остальные
    """
    priorities = user_data.get('priorities', [])
    
    # Разделяем на ХИТы и обычные
    hit_tours = []
    regular_tours = []
    
    for tour in tours:
        if tour.get("ХИТ", "").strip():
            hit_tours.append(tour)
        else:
            regular_tours.append(tour)
    
    # Если нет ХИТов - просто ранжируем обычные
    if not hit_tours:
        return rank_tours_by_priorities(regular_tours, user_data)
    
    # Ранжируем ХИТы по приоритетам
    ranked_hits = rank_tours_by_priorities(hit_tours, user_data)
    
    # Ранжируем остальные
    ranked_regular = rank_tours_by_priorities(regular_tours, user_data)
    
    # Возвращаем: сначала ХИТы, потом остальные
    return ranked_hits + ranked_regular

def rank_tours_by_priorities(tours, user_data):
    """
    Ранжирует экскурсии по приоритетам пользователя
    """
    priorities = user_data.get('priorities', [])
    
    if not priorities or not tours:
        return tours
    
    scored_tours = []
    
    for tour in tours:
        score = 0
        tour_name = tour.get("Название", "").lower()
        tour_description = tour.get("Описание", "").lower()
        tour_price = tour.get("Цена Взр", "")
        
        # Проверяем каждый приоритет
        for priority in priorities:
            if priority == 'комфорт':
                if any(keyword in tour_name or keyword in tour_description 
                      for keyword in ['комфорт', 'люкс', 'vip', 'индивидуал', 'част']):
                    score += 3
                elif 'маленьк' in tour_description or 'минигрупп' in tour_description:
                    score += 2
            
            elif priority == 'бюджет':
                try:
                    # Пробуем извлечь цену
                    price = int(''.join(filter(str.isdigit, tour_price)))
                    if price < 2000:  # Дешевые экскурсии
                        score += 3
                    elif price < 3500:  # Средние по цене
                        score += 1
                except:
                    pass
            
            elif priority == 'фотографии':
                if any(keyword in tour_name or keyword in tour_description 
                      for keyword in ['фото', 'instagram', 'инстаграм', 'красив', 'живописн', 'панорам']):
                    score += 3
            
            elif priority == 'не рано вставать':
                start_time = tour.get("Время начала", "").lower()
                if start_time and 'утр' in start_time:
                    # Если начинается позже 9 утра
                    if '9' in start_time or '10' in start_time or '11' in start_time:
                        score += 3
                    elif '8' not in start_time and '7' not in start_time:
                        score += 2
                elif not start_time:  # Если время не указано, предполагаем что не рано
                    score += 1
            
            elif priority == 'без толп':
                if any(keyword in tour_description 
                      for keyword in ['маленьк групп', 'индивидуал', 'част', 'уединен']):
                    score += 3
                elif 'групп' in tour_description and 'больш' not in tour_description:
                    score += 1
        
        scored_tours.append((score, tour))
    
    # Сортируем по убыванию баллов
    scored_tours.sort(key=lambda x: x[0], reverse=True)
    
    # Возвращаем только экскурсии (без баллов)
    return [tour for _, tour in scored_tours]

# ==================== ФОРМАТИРОВАНИЕ ОПИСАНИЙ (НОВОЕ - в стиле Алекса) ====================
def format_tour_card_compact(tour, index=None):
    """
    Форматирует тур в компактную КАРТОЧКУ без излишеств.
    Подходит для списков и группировки.
    """
    name = tour.get("Название", "Без названия").replace("ХИТ", "").strip()
    price_adult = tour.get("Цена Взр", "?")
    price_child = tour.get("Цена Дет", "")
    vitrina = tour.get("Описание (Витрина)", "")
    is_hit = "ХИТ" in tour.get("Название", "")
    
    # Первое предложение описания (макс 80 символов)
    desc_short = vitrina.split('.')[0][:80].strip() if vitrina else ""
    
    # Номер в списке
    num_prefix = f"{index}. " if index else ""
    
    # Формируем карточку
    if is_hit:
        card = f"🏆 {num_prefix}*{name}*\n"
    else:
        card = f"{num_prefix}*{name}*\n"
    
    if desc_short:
        card += f"_{desc_short}_\n"
    
    card += f"💰 {price_adult}฿"
    if price_child and price_child != "⛔️":
        card += f" / {price_child}฿ (дет.)"
    
    return card

def format_tours_group(tours, title="", user_name="", show_tips=True):
    """
    Форматирует группу туров с разделителем и подсказкой.
    Минималистично, без излишеств.
    """
    if not tours:
        return ""
    
    result = ""
    
    # Заголовок группы
    if title:
        result += f"\n{title}\n"
        result += "─" * 40 + "\n\n"
    
    # Персонализированная подсказка перед ХИТами
    if title and "ХИТ" in title and user_name and show_tips:
        result += f"✨ {user_name}, это наши звёзды - 99% гостей в восторге!\n\n"
    
    # Карточки туров
    for i, tour in enumerate(tours, 1):
        result += format_tour_card_compact(tour, i)
        result += "\n"
    
    return result

def format_tour_description_alex_style(tour):
    """
    Форматирует описание экскурсии в ТОЧНОМ стиле Алекса из промта
    Использует только данные из CSV, без выдумок
    """
    # Получаем данные из ТОЧНЫХ полей CSV
    name = tour.get("Название", "Без названия")
    vitrina_desc = tour.get("Описание (Витрина)", "")
    honest_review = tour.get("Честный обзор", "")
    price_adult = tour.get("Цена Взр", "Уточняйте")
    price_child = tour.get("Цена Дет", "")
    link = tour.get("Ссылка", "")
    prepayment = tour.get("Предоплата", "50%")
    tags = tour.get("Теги (Безопасность)", "")
    category = tour.get("Для информации", "")
    
    # Убираем слово ХИТ из названия для чистоты, но запоминаем
    display_name = name
    is_hit = False
    if "ХИТ" in name:
        is_hit = True
        # Аккуратно убираем ХИТ из отображаемого имени
        display_name = display_name.replace("ХИТ", "").strip()
        if display_name.startswith(",") or display_name.startswith(";"):
            display_name = display_name[1:].strip()
    
    # Определяем эмодзи по категории
    if "Море" in category:
        emoji = "🌊"
    elif "Рыбалка" in category:
        emoji = "🎣"
    elif "Яхты" in category:
        emoji = "🛥️"
    elif "Суша" in category and "активные" in category.lower():
        emoji = "🚴"
    elif "Суша" in category and "семейные" in category.lower():
        emoji = "👨‍👩‍👧‍👦"
    elif "Суша" in category and "обзорные" in category.lower():
        emoji = "🏞️"
    elif "Вечерние" in category:
        emoji = "🎭"
    elif "Туры в другие страны" in category:
        emoji = "🌍"
    else:
        emoji = "✨"
    
    # ========== ФОРМАТИРУЕМ ПО ШАБЛОНУ ИЗ ПРОМТА ==========
    
    formatted = ""
    
    # 1. Заголовок с ХИТ и эмодзи (ТОЧНО как в промте)
    if is_hit:
        formatted += f"**(ХИТ) {emoji} {display_name}**\n\n"
    else:
        formatted += f"{emoji} **{display_name}**\n\n"
    
    # 2. "Вкусная" фраза из описания витрины
    if vitrina_desc:
        # Берем первое предложение или первые 150 символов
        sentences = vitrina_desc.split('.')
        if len(sentences) > 1:
            first_sentence = sentences[0].strip() + '.'
        else:
            first_sentence = vitrina_desc[:150].strip()
            if len(vitrina_desc) > 150:
                first_sentence += '...'
        
        if first_sentence:
            formatted += f"_{first_sentence}_\n\n"
    
    # 3. "✨ Почему это отлично?" (на основе тегов)
    if tags:
        formatted += "**✨ Почему это отлично?**\n"
        
        # Преобразуем хэштеги в читаемые пункты
        tag_descriptions = []
        tag_text = tags.lower()
        
        # Маппинг тегов (сначала проверяем самые важные)
        tag_mappings = [
            ("#нельзя_беременным", "• *Не подходит беременным*"),
            ("#дети_от_1_года", "• *Детям от 1 года*"),
            ("#комфорт", "• *Максимальный комфорт*"),
            ("#релакс", "• *Идеально для релакса*"),
            ("#бюджетно", "• *Отличное соотношение цены и качества*"),
            ("#ранний_выезд", "• *Ранний выезд для пустых пляжей*"),
            ("#без_толп", "• *Минимум туристов*"),
            ("#снорклинг", "• *Лучший снорклинг*"),
            ("#пляж", "• *Райские пляжи*"),
            ("#романтика", "• *Идеально для пар*"),
            ("#семейный", "• *Отлично подходит для семьи*"),
            ("#vip", "• *VIP-сервис*"),
            ("#премиум", "• *Премиум-уровень*"),
            ("#тусовка", "• *Веселая тусовка*"),
            ("#активно", "• *Для активных туристов*"),
            ("#фото", "• *Лучшие фото для Instagram*"),
            ("#инстаграм", "• *Instagram-мечта*"),
            ("#мальдивы", "• *Как на Мальдивах*"),
            ("#эксклюзив", "• *Эксклюзивный тур*"),
            ("#нет_волн", "• *Без волн и качки*"),
        ]
        
        for tag_pattern, description in tag_mappings:
            if tag_pattern in tag_text:
                tag_descriptions.append(description)
        
        # Если мало тегов, добавляем общие (но не больше 4 всего)
        if len(tag_descriptions) < 2:
            general_tags = [
                "• *Незабываемые впечатления*",
                "• *Профессиональная организация*",
                "• *Безопасность и комфорт*",
                "• *Лучшие гиды Пхукета*"
            ]
            # Добавляем общие теги, чтобы было 3-4 пункта
            while len(tag_descriptions) < 3 and general_tags:
                tag_descriptions.append(general_tags.pop(0))
        
        # Показываем не больше 4 тегов
        for desc in tag_descriptions[:4]:
            formatted += f"{desc}\n"
        
        formatted += "\n"
    else:
        # Если тегов нет, добавляем стандартные преимущества
        formatted += "**✨ Почему это отлично?**\n"
        formatted += "• *Незабываемые впечатления*\n"
        formatted += "• *Профессиональная организация*\n"
        formatted += "• *Безопасность и комфорт*\n\n"
    
    # 4. "⚡️ Честно от местных:"
    if honest_review and honest_review.strip():
        # Берем первое предложение или первые 120 символов
        honest_clean = honest_review.strip()
        sentences = honest_clean.split('.')
        if len(sentences) > 1:
            first_sentence = sentences[0].strip() + '.'
        else:
            first_sentence = honest_clean[:120].strip()
            if len(honest_clean) > 120:
                first_sentence += '...'
        
        if first_sentence:
            formatted += f"**⚡️ Честно от местных:**\n"
            formatted += f"_{first_sentence}_\n\n"
    
    # 5. "💰 Стоимость:" (точно как в CSV)
    price_adult_clean = str(price_adult).strip()
    price_child_clean = str(price_child).strip() if price_child else ""
    
    formatted += f"**💰 Стоимость:** **{price_adult_clean} бат** / взрослый"
    
    if price_child_clean and price_child_clean != "⛔️" and price_child_clean != "Уточняйте":
        formatted += f", **{price_child_clean} бат** / ребенок\n"
    else:
        formatted += "\n"
    
    # 6. Предоплата (точно как в CSV)
    prepayment_clean = str(prepayment).strip()
    formatted += f"**💳 Предоплата:** {prepayment_clean}\n\n"
    
    # 7. Ссылка (если есть и это реальная ссылка)
    if link and "http" in link:
        # Очищаем ссылку от лишних пробелов
        clean_link = link.strip()
        formatted += f"**📖 Подробности и фото:** [Смотреть на сайте]({clean_link})\n"
    
    return formatted

def get_tour_additional_info(tour):
    """
    Возвращает дополнительную информацию об экскурсии
    Используется при запросе пользователя
    Возвращает ТОЛЬКО данные из CSV
    """
    name = tour.get("Название", "")
    days = tour.get("Дни выезда", "")
    guide = tour.get("Гид", "")
    food = tour.get("Питание", "")
    what_to_take = tour.get("Что взять с собой", "")
    important_info = tour.get("Важная информация", "")
    keywords = tour.get("Ключевые слова", "")
    
    info_text = f"**📋 Дополнительная информация:**\n\n"
    
    info_added = False
    
    if days and days.strip():
        info_text += f"**📅 Дни выезда:** {days}\n\n"
        info_added = True
    
    if guide and guide.strip() and guide.strip().lower() != "нет":
        info_text += f"**🗣 Гид:** {guide}\n\n"
        info_added = True
    
    if food and food.strip():
        info_text += f"**🍽 Питание:** {food}\n\n"
        info_added = True
    
    if what_to_take and what_to_take.strip():
        info_text += f"**🎒 Что взять с собой:**\n{what_to_take}\n\n"
        info_added = True
    
    if important_info and important_info.strip():
        # Берем только первые 3 пункта или первые 300 символов
        important_clean = important_info.strip()
        if len(important_clean) > 300:
            important_clean = important_clean[:300] + "..."
        info_text += f"**⚠️ Важная информация:**\n{important_clean}\n\n"
        info_added = True
    
    if not info_added:
        info_text += "*Дополнительная информация по запросу у менеджера* ✅\n"
    
    return info_text

# ==================== СОЗДАНИЕ ИНЛАЙН-КНОПОК ДЛЯ ЭКСКУРСИЙ ====================
def make_tours_keyboard(tours, offset=0, limit=5, show_question_button=True):
    """
    Создает инлайн-клавиатуру для выбора экскурсий
    """
    keyboard = []
    
    for i in range(offset, min(offset + limit, len(tours))):
        tour = tours[i]
        name = tour.get("Название", f"Экскурсия {i+1}")
        
        # Очищаем название от ХИТ для отображения
        display_name = name.replace("ХИТ", "").strip()
        if display_name.startswith(",") or display_name.startswith(";"):
            display_name = display_name[1:].strip()
        
        # Обрезаем слишком длинные названия
        if len(display_name) > 30:
            display_name = display_name[:27] + "..."
        
        # Добавляем эмодзи хитов и нумерацию
        if "ХИТ" in name:
            display_name = f"🏆 {display_name}"
        
        keyboard.append([InlineKeyboardButton(f"{i+1}. {display_name}", callback_data=f"tour_{i}")])
    
    # Кнопки навигации
    nav_buttons = []
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Предыдущие", callback_data=f"prev_{offset-limit}"))
    
    if offset + limit < len(tours):
        nav_buttons.append(InlineKeyboardButton("Показать ещё ▶️", callback_data=f"next_{offset+limit}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # ⭐ ДОБАВИЛИ КНОПКУ "ЗАДАТЬ ВОПРОС"
    if show_question_button:
        keyboard.append([InlineKeyboardButton("🤔 Задать вопрос", callback_data="ask_question")])
    
    keyboard.append([InlineKeyboardButton("🔄 Выбрать другую категорию", callback_data="change_category")])
    
    return InlineKeyboardMarkup(keyboard)

# ==================== ФУНКЦИИ АНАЛИТИКИ ====================
def track_user_session(context, stage, additional_data=None):
    """Отслеживает сессию пользователя для анализа уходов"""
    if 'session_start' not in context.user_data:
        context.user_data['session_start'] = datetime.now()
        context.user_data['session_stages'] = []
    
    context.user_data['current_stage'] = stage
    context.user_data['session_stages'].append({
        'stage': stage,
        'timestamp': datetime.now(),
        'data': additional_data
    })

def log_drop_off_if_needed(user_id, context):
    """Логирует уход пользователя, если он не завершил диалог"""
    if context.user_data.get('current_stage'):
        session_duration = None
        if 'session_start' in context.user_data:
            session_duration = (datetime.now() - context.user_data['session_start']).seconds
        
        logger.log_drop_off(
            user_id=user_id,
            drop_off_stage=context.user_data['current_stage'],
            last_action=context.user_data.get('last_action', 'unknown'),
            session_duration=session_duration,
            user_profile=context.user_data.get('user_data')
        )
# ==================== КОНЕЦ ФУНКЦИЙ АНАЛИТИКИ ====================

# ==================== КОМАНДЫ БОТА ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user

    # ОЧИЩАЕМ КОНТЕКСТ - позволяет разным пользователям с одного телефона начать сначала
    context.user_data.clear()
    
# === АНАЛИТИКА: ТРЕКИНГ СЕССИИ ===
    track_user_session(context, BOT_STAGES['start'])
    logger.log_action(user.id, "started_bot", stage=BOT_STAGES['start'])
    context.user_data['last_action'] = 'start'
    # === КОНЕЦ АНАЛИТИКИ ===

    welcome_text = f"""Приветствую, {user.first_name}! 🙏

Я Алекс, ваш личный гид по сокровищам Пхукета от GoldenKeyTours.

Я помогу превратить ваши "хочу" в незабываемые впечатления. Подскажите, о чём мечтаете?

💡 *Совет:* 
• Нажмите на кнопку категории ниже
• Или напишите, что вас интересует (например: "слонов" 🐘, "аватара", "рыбалку")
• Можете задать вопрос о Пхукете"""
    
    # Показываем typing indicator перед приветствием
    await update.effective_chat.send_chat_action(ChatAction.TYPING)
    await asyncio.sleep(0.5)
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=make_category_keyboard()
    )
    return CATEGORY

async def handle_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пользователь выбрал категорию или написал что-то"""
    user_choice = update.message.text
    user = update.effective_user
    
    # ПРОВЕРЯЕМ КНОПКУ "НОВЫЙ ПОИСК" - сбрасываем контекст и начинаем заново
    if user_choice == "🔄 Новый поиск":
        context.user_data.clear()
        
        welcome_text = f"""Хорошо, начнём с чистого листа! 📋

Расскажите мне о своей группе - кто едет?"""
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=make_category_keyboard()
        )
        return CATEGORY
    
    # === ВИЗУАЛЬНЫЙ ЭФФЕКТ - TYPING INDICATOR ===
    try:
        await update.effective_chat.send_chat_action(ChatAction.TYPING)
        await asyncio.sleep(0.5)
    except:
        pass
    
    valid_categories = get_categories()
    
    # ════════════════════════════════════════════════════════════════════════
    # ЛОГИКА: 1) Это категория? 2) Нет? → Ищем туры по ключевым словам
    # 3) Найдены? → Показываем 4) Нет? → Это вопрос? → DeepSeek
    # 5) Ничего? → Ошибка
    # ════════════════════════════════════════════════════════════════════════
    
    # ВАРИАНТ 1: ЭТО СТАНДАРТНАЯ КАТЕГОРИЯ
    if user_choice in valid_categories:
        # === АНАЛИТИКА ===
        track_user_session(context, BOT_STAGES['category_selection'], {'category': user_choice})
        logger.log_action(user.id, "chose_category", stage=BOT_STAGES['category_selection'], category=user_choice)
        context.user_data['last_action'] = 'category_choice'
        # === КОНЕЦ АНАЛИТИКИ ===
        
        # Проверяем ограничения (беременность, маленькие дети + Море)
        if 'user_data' in context.user_data:
            user_data = context.user_data.get('user_data', {})
            is_pregnant = user_data.get('pregnant', False)
            children_ages = user_data.get('children', [])
            has_young_children = any(age < 12 for age in children_ages)
            
            if (is_pregnant or has_young_children) and "Море" in user_choice:
                response = "⚠️ *Внимание!*\n\n"
                
                if is_pregnant:
                    response += "🤰 *Беременным* = ❌ **ВСЕ** морские туры\n"
                
                if has_young_children:
                    response += "👶 *Детям до года* = ❌ **ВСЕ** морские туры\n"
                
                response += "\n🎯 *Лучше выбрать:*\n"
                response += "• 🏞️ *Суша (обзорные)* — Аватар, смотровые\n"
                response += "• 🐘 *Суша (семейные)* — слоны, аквапарк\n"
                response += "• 🎭 *Вечерние шоу* — Сиам Нирамит\n\n"
                response += "*Продолжить с Морем или выбрать другую категорию?*"
                
                keyboard = [
                    ["🌊 Продолжить с Морем"],
                    ["🔄 Выбрать другую категорию"]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
                
                await update.message.reply_text(response, parse_mode='Markdown', reply_markup=reply_markup)
                context.user_data['pending_category'] = user_choice
                return CATEGORY
        
        # Нет ограничений - продолжаем обычно
        context.user_data['category'] = user_choice
        
        if 'user_data' in context.user_data and context.user_data['user_data']:
            return await proceed_to_tours(update, context, context.user_data['user_data'])
        
        # Запрашиваем данные пользователя
        category_tours = [t for t in TOURS if t.get("Для информации", "") == user_choice]
        context.user_data['filtered_tours'] = category_tours
        
        hit_tours = [t for t in category_tours if "ХИТ" in t.get("Название", "")]
        
        response = f"Отлично! Выбрана категория: *{user_choice}*\n\n"
        
        if hit_tours:
            hit_count = len(hit_tours)
            if hit_count == 1:
                hit_text = "1 *ХИТ*"
            elif hit_count in [2, 3, 4]:
                hit_text = f"{hit_count} *ХИТА*"
            else:
                hit_text = f"{hit_count} *ХИТОВ*"
            response += f"В этой категории у нас есть {hit_text}! 🏆\n"
            response += "Давайте я подберу для вас самые популярные варианты.\n\n"
        else:
            response += "Давайте я подберу для вас лучшие варианты.\n\n"
        
        response += "Но сначала мне нужно уточнить несколько деталей:\n\n"
        response += "1️⃣ *Состав группы:* Сколько взрослых и детей? Укажите возраст каждого ребенка (например: 8 лет, 3 года, менее 1 года).\n"
        response += "2️⃣ *Беременность:* Есть ли беременные в группе?\n"
        response += "3️⃣ *Что важно:* Комфорт, бюджет, фотографии, не любите рано вставать?\n"
        response += "4️⃣ *Здоровье:* Проблемы со спиной, укачивание, сложности с ходьбой?\n\n"
        response += "Ответьте, пожалуйста, одним сообщением. Например:\n"
        response += "_«2 взрослых, ребенок 5 лет, не беременны, хотим комфорт и не рано вставать»_"
        
        await update.message.reply_text(response, parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
        return QUALIFICATION
    
    # ВАРИАНТ 2: НЕ КАТЕГОРИЯ - СНАЧАЛА ИЩЕМ ТУРЫ ПО КЛЮЧЕВЫМ СЛОВАМ
    matching_tours = search_tours_by_keywords(user_choice)
    
    if matching_tours:
        # ✅ НАЙДЕНЫ ТУРЫ ПО КЛЮЧЕВЫМ СЛОВАМ!
        categories_with_tours = {}
        for tour, category, relevance in matching_tours[:15]:
            if category not in categories_with_tours:
                categories_with_tours[category] = []
            categories_with_tours[category].append(tour)
        
        first_category = list(categories_with_tours.keys())[0]
        sample_tours = categories_with_tours[first_category][:2]
        
        tour_examples = "\n".join([f"• {t.get('Название', 'Тур')}" for t in sample_tours])
        
        deepseek_comment = generate_deepseek_response(
            user_query=f"Пользователь спросил про: {user_choice}. Я нашел {len(matching_tours)} туров по этому запросу. "
                       f"Вот примеры: {tour_examples}",
            tour_data=None,
            context_info=f"Результаты поиска по запросу пользователя: {user_choice}. Категория: {first_category}",
            user_name=user.first_name
        )
        
        deepseek_comment = format_deepseek_answer(deepseek_comment)
        
        await update.message.reply_text(deepseek_comment, parse_mode='Markdown')
        
        tours_to_show = categories_with_tours[first_category]
        
        context.user_data['selected_category'] = first_category
        context.user_data['ranked_tours'] = tours_to_show
        context.user_data['tour_offset'] = 0
        
        await update.message.reply_text(
            format_tours_group(tours_to_show[:5]),
            parse_mode='Markdown',
            reply_markup=make_tours_keyboard(tours_to_show, 0, 5)
        )
        
        # === АНАЛИТИКА ===
        track_user_session(context, BOT_STAGES['category_selection'], {'search_query': user_choice})
        logger.log_action(user.id, "searched_tours", stage=BOT_STAGES['category_selection'], query=user_choice, found=len(matching_tours))
        context.user_data['last_action'] = 'search_query'
        # === КОНЕЦ АНАЛИТИКИ ===
        
        return TOUR_DETAILS
    
    # ВАРИАНТ 3: ТУРЫ НЕ НАЙДЕНЫ - ПРОВЕРЯЕМ, ЭТО ВОПРОС?
    if is_likely_question(user_choice):
        # ✅ ЭТО ВОПРОС - ОТВЕЧАЕМ DEEPSEEK
        await update.effective_chat.send_chat_action(ChatAction.TYPING)
        await asyncio.sleep(1)
        
        deepseek_answer = generate_deepseek_response(
            user_query=user_choice,
            tour_data=None,
            context_info="Пользователь еще не выбрал категорию, задает вопрос о Пхукете",
            user_name=user.first_name
        )
        
        deepseek_answer = format_deepseek_answer(deepseek_answer)
        
        await update.message.reply_text(deepseek_answer, parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
        
        await update.message.reply_text(
            "📋 *Теперь выбирайте категорию экскурсий:*",
            parse_mode='Markdown',
            reply_markup=make_category_keyboard()
        )
        
        # === АНАЛИТИКА ===
        track_user_session(context, BOT_STAGES['category_selection'])
        logger.log_action(user.id, "asked_question_at_category", stage=BOT_STAGES['category_selection'], query=user_choice)
        context.user_data['last_action'] = 'category_question'
        # === КОНЕЦ АНАЛИТИКИ ===
        
        return CATEGORY
    
    # ВАРИАНТ 4: НИЧЕГО НЕ ПОДХОДИТ - ОШИБКА ВВОДА
    await update.message.reply_text(
        f"🤔 *'{user_choice}'* - это не стандартная категория экскурсий.\n\n"
        "🎯 *Как выбрать экскурсию:*\n"
        "• Нажмите на одну из кнопок ниже\n"
        "• Или напишите, что вас интересует (слонов, дельфинов, храмы, рыбалку, яхту)\n"
        "• Или задайте вопрос о Пхукете!\n\n"
        "📝 *Доступные категории:*\n" + "\n".join(f"• {cat}" for cat in valid_categories) + "\n\n"
        "💡 *Примеры поиска:* \"слонов\" 🐘, \"аватара\" 🎬, \"рыбалку\" 🎣, \"яхту\" ⛵",
        parse_mode='Markdown',
        reply_markup=make_category_keyboard()
    )
    return CATEGORY

async def handle_category_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора после предупреждения о море"""
    user_choice = update.message.text
    
    if user_choice.startswith("🌊 Продолжить с Морем"):
        # Берём сохранённую категорию
        category = context.user_data.get('pending_category', 'Море (Острова)')
        context.user_data['category'] = category
        
        # Проверяем, есть ли уже данные пользователя
        if 'user_data' in context.user_data and context.user_data['user_data']:
            # Данные уже есть - показываем морские туры для ознакомления
            user_data = context.user_data['user_data']
            
            # Фильтруем морские туры (даже если они не подходят по ограничениям)
            sea_tours = [t for t in TOURS if t.get("Для информации", "") == category]
            context.user_data['ranked_tours'] = sea_tours
            context.user_data['tour_offset'] = 0
            
            response = f"🌊 *Морские экскурсии ({len(sea_tours)} вариантов):*\n\n"
            
            # Проверяем ограничения
            is_pregnant = user_data.get('pregnant', False)
            children_ages = user_data.get('children', [])
            has_young_children = any(age < 12 for age in children_ages)
            
            if is_pregnant or has_young_children:
                response += "⚠️ *Внимание:* Эти экскурсии не рекомендуются для вашей группы по медицинским показаниям.\n"
                response += "Показываю только для ознакомления - бронирование будет недоступно.\n\n"
                context.user_data['sea_readonly'] = True  # Флаг для запрета бронирования
            else:
                response += "Отличный выбор! Вот все доступные варианты.\n\n"
            
            await update.message.reply_text(
                response,
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardRemove()
            )
            
            await update.message.reply_text(
                "Выберите экскурсию для подробностей:",
                reply_markup=make_tours_keyboard(sea_tours, 0, 5, show_question_button=True)
            )
            
            # Убираем pending_category
            if 'pending_category' in context.user_data:
                del context.user_data['pending_category']
            
            return TOUR_DETAILS
        else:
            # Данных нет - запрашиваем
            response = f"Отлично! Выбрана категория: *{category}*\n\n"
            
            response += "Давайте я подберу для вас лучшие варианты.\n\n"
            response += "Но сначала мне нужно уточнить несколько деталей:\n\n"
            response += "1️⃣ *Состав группы:* Сколько взрослых и детей? Укажите возраст каждого ребенка (например: 8 лет, 3 года, менее 1 года).\n"
            response += "2️⃣ *Беременность:* Есть ли беременные в группе?\n"
            response += "3️⃣ *Что важно:* Комфорт, бюджет, фотографии, не любите рано вставать?\n"
            response += "4️⃣ *Здоровье:* Проблемы со спиной, укачивание, сложности с ходьбой?\n\n"
            response += "Ответьте, пожалуйста, одним сообщением. Например:\n"
            response += "_«2 взрослых, ребенок 5 лет, не беременны, хотим комфорт и не рано вставать»_"
            
            await update.message.reply_text(
                response,
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardRemove()
            )
            
            # Убираем pending_category
            if 'pending_category' in context.user_data:
                del context.user_data['pending_category']
            
            return QUALIFICATION
    
    elif user_choice == "🔄 Выбрать другую категорию":
        # Показываем категории заново
        await update.message.reply_text(
            "🔄 Выбирайте категорию:",
            reply_markup=make_category_keyboard()
        )
        
        # Убираем pending_category
        if 'pending_category' in context.user_data:
            del context.user_data['pending_category']
        
        return CATEGORY

async def handle_qualification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пользователь ответил на вопросы - анализируем и уточняем при необходимости"""
    user_text = update.message.text
    
    # === АНАЛИТИКА ===
    user = update.effective_user
    track_user_session(context, BOT_STAGES['data_collection'])
    logger.log_action(user.id, "provided_user_data", stage=BOT_STAGES['data_collection'])
    context.user_data['last_action'] = 'user_data_input'
    
    # Анализируем ответ
    user_data, missing_points = parse_user_response(user_text)
    
    # Сохраняем частичные данные
    save_partial_data(context, user_data)
    
    # Получаем текущие данные
    current_data = context.user_data['user_data']
    
    # Проверяем, что ещё не поняли
    current_missing = check_missing_points(current_data)
    
    # Если всё поняли - показываем финальное подтверждение
    if not current_missing:
        await show_final_confirmation(update, context, current_data)
        return CONFIRMATION
    
    # Если что-то не поняли - уточняем
    await ask_for_clarification(update, context, current_data, current_missing)
    return CONFIRMATION

async def handle_adults_clarification(update: Update, context: ContextTypes.DEFAULT_TYPE, user_text, user_data):
    """Обработка уточнения количества взрослых"""
    import re
    
    # Словарь числительных
    number_words = {
        'один': 1, 'одного': 1, 'одной': 1,
        'два': 2, 'двое': 2, 'двух': 2,
        'три': 3, 'трое': 3, 'трёх': 3, 'трех': 3,
        'четыре': 4, 'четверо': 4, 'четырех': 4, 'четырёх': 4,
        'пять': 5, 'пятеро': 5,
        'шесть': 6, 'шестеро': 6,
        'семь': 7, 'семеро': 7,
        'восемь': 8, 'восьмеро': 8,
        'девять': 9, 'девятеро': 9,
        'десять': 10
    }
    
    text_lower = user_text.lower()
    
    # 1. Ищем цифры
    numbers = re.findall(r'\d+', user_text)
    if numbers:
        adults = int(numbers[0])
    
    # 2. Ищем числительные
    elif any(word in text_lower for word in number_words.keys()):
        for word, num in number_words.items():
            if word in text_lower:
                adults = num
                break
    else:
        await update.message.reply_text(
            "Пожалуйста, укажите число взрослых (например: '2', 'двое', 'нас трое')",
            reply_markup=ReplyKeyboardRemove()
        )
        return CONFIRMATION
    
    user_data['adults'] = adults
    response = f"✅ Запомнил: {adults} взрослых\n"
    
    # Убираем вопрос
    if 'next_question' in context.user_data:
        del context.user_data['next_question']
    
    # Проверяем, всё ли поняли
    current_missing = check_missing_points(user_data)
    
    if not current_missing:
        await show_final_confirmation(update, context, user_data)
    else:
        await ask_for_clarification(update, context, user_data, current_missing)
    
    return CONFIRMATION

async def handle_children_clarification(update: Update, context: ContextTypes.DEFAULT_TYPE, user_text, user_data):
    """Обработка уточнения информации о детях"""
    parsed_data, _ = parse_user_response(user_text)
    
    if parsed_data['children'] or "нет" in user_text.lower() or "без" in user_text.lower():
        # Сохраняем данные о детях
        save_partial_data(context, parsed_data)
        
        # Убираем вопрос
        if 'next_question' in context.user_data:
            del context.user_data['next_question']
        
        # Проверяем, всё ли поняли
        current_data = context.user_data['user_data']
        current_missing = check_missing_points(current_data)
        
        if not current_missing:
            await show_final_confirmation(update, context, current_data)
        else:
            await ask_for_clarification(update, context, current_data, current_missing)
        
        return CONFIRMATION
    
    else:
        await update.message.reply_text(
            "Пожалуйста, укажите возраст детей или напишите 'нет детей' (например: 5 лет, 3 года, 6 месяцев)",
            reply_markup=ReplyKeyboardRemove()
        )
        return CONFIRMATION

async def handle_pregnant_clarification(update: Update, context: ContextTypes.DEFAULT_TYPE, user_text, user_data):
    """Обработка уточнения беременности"""
    text_lower = user_text.lower()
    
    if any(word in text_lower for word in ['да', 'беремен', 'в положении', 'жду']):
        user_data['pregnant'] = True
        response = "✅ Запомнил: есть беременные\n"
    elif any(word in text_lower for word in ['нет', 'не беремен', 'не в положении']):
        user_data['pregnant'] = False
        response = "✅ Запомнил: нет беременных\n"
    else:
        await update.message.reply_text(
            "Пожалуйста, ответьте Да или Нет: есть ли беременные в группе?",
            reply_markup=ReplyKeyboardRemove()
        )
        return CONFIRMATION
    
    # Убираем вопрос
    if 'next_question' in context.user_data:
        del context.user_data['next_question']
    
    # Проверяем, всё ли поняли
    current_missing = check_missing_points(user_data)
    
    if not current_missing:
        await show_final_confirmation(update, context, user_data)
    else:
        await ask_for_clarification(update, context, user_data, current_missing)
    
    return CONFIRMATION

async def handle_confirmation_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора из кнопок подтверждения"""
    user_choice = update.message.text
    user_data = context.user_data.get('user_data', {})
    
    if user_choice == "✅ Да, всё верно":
        # ВСЁ заполнено - показываем экскурсии
        return await proceed_to_tours(update, context, user_data)
    
    elif user_choice == "✏️ Нет, исправить":
        # Возвращаемся к вводу данных
        response = "✏️ *Хорошо, давайте исправим!*\n\n"
        response += "Напишите, *что именно* нужно исправить:\n\n"
        response += "👨‍👩‍👧‍👦 *Количество взрослых:* '2 взрослых', 'нас трое', 'взрослых 1'\n"
        response += "👶 *Информация о детях:* '2 детей: 5 лет и 3 года', '1 ребенок 2 года', 'нет детей'\n"
        response += "🤰 *Беременность:* 'нет беременности', 'беременна'\n"
        response += "🎯 *Что важно:* 'комфорт', 'бюджет', 'не рано вставать'\n"
        response += "🏥 *Здоровье:* 'спина', 'укачивание'\n\n"
        response += "*Примеры:*\n"
        response += "• 'исправьте: взрослых 2, нет детей'\n"
        response += "• 'дети: 5 лет и 3 года'\n"
        response += "• 'беременности нет, хотим комфорт'\n\n"
        response += "*Просто напишите исправления — я всё пойму!*"
    
        # Устанавливаем флаг, что сейчас будет исправление
        context.user_data['waiting_for_correction'] = True
    
        await update.message.reply_text(
            response,
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        return CONFIRMATION  # Остаёмся в CONFIRMATION, а не возвращаемся в QUALIFICATION

    elif user_choice == "🔄 Выбрать другую категорию":
        # Возврат к выбору категории
        await update.message.reply_text(
            "🔄 Возвращаюсь к выбору категории...",
            reply_markup=ReplyKeyboardRemove()
        )
        await update.message.reply_text(
            "Выберите категорию экскурсий:",
            reply_markup=make_category_keyboard()
        )
        return CATEGORY

    elif user_choice == "✏️ Изменить параметры":
        # Возврат к уточнению параметров
        await update.message.reply_text(
            "Давайте уточним параметры поиска:",
            reply_markup=ReplyKeyboardRemove()
        )
        # Показываем текущие данные и спрашиваем что изменить
        current_data = context.user_data.get('user_data', {})
        current_missing = check_missing_points(current_data)
        await ask_for_clarification(update, context, current_data, current_missing)
        return CONFIRMATION

    elif user_choice == "📋 Показать все":
        # Показываем все экскурсии без фильтрации
        category = context.user_data.get('category', 'неизвестно')
        category_tours = context.user_data.get('filtered_tours', [])
        
        context.user_data['ranked_tours'] = category_tours
        context.user_data['tour_offset'] = 0
        
        response = f"📋 *Все экскурсии категории {category} ({len(category_tours)} вариантов):*\n"
        response += "⚠️ *Внимание:* Некоторые экскурсии могут не подходить по вашим критериям\n\n"
        
        await update.message.reply_text(
            response,
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        
        await update.message.reply_text(
            "Выберите экскурсию для подробностей:",
            reply_markup=make_tours_keyboard(category_tours, 0, 5, show_question_button=True)
        )
        
        return TOUR_DETAILS
        # Возврат к уточнению параметров (то же, что "Изменить параметры")
        await update.message.reply_text(
            "Давайте уточним параметры поиска:",
            reply_markup=ReplyKeyboardRemove()
        )
        # Показываем текущие данные и спрашиваем что изменить
        current_data = context.user_data.get('user_data', {})
        current_missing = check_missing_points(current_data)
        await ask_for_clarification(update, context, current_data, current_missing)
        return CONFIRMATION

    elif user_choice == "📋 Только ознакомиться с морскими":
        # Показываем морские экскурсии, несмотря на ограничения
        category = "Море"
        category_tours = [tour for tour in TOURS if tour.get("Для информации", "").strip() == "Море"]
        
        context.user_data['ranked_tours'] = category_tours
        context.user_data['tour_offset'] = 0
        
        response = f"📋 *Морские экскурсии ({len(category_tours)} вариантов):*\n"
        response += "⚠️ *Внимание:* Эти экскурсии не рекомендуются для вашей группы по медицинским показаниям\n\n"
        
        await update.message.reply_text(
            response,
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        
        await update.message.reply_text(
            "Выберите экскурсию для подробностей:",
            reply_markup=make_tours_keyboard(category_tours, 0, 5, show_question_button=True)
        )
        
        return TOUR_DETAILS
    
    elif user_choice == "🔄 Подобрать из рекомендованных":
        # Показываем экскурсии из рекомендованных категорий (суша и шоу)
        user_data = context.user_data.get('user_data', {})
        
        # Фильтруем все туры, исключая морские
        all_tours = context.bot_data.get('tours', TOURS)
        recommended_tours = [tour for tour in all_tours if tour.get("Для информации", "").strip() != "Море"]
        
        # Сохраняем отфильтрованные туры
        context.user_data['category'] = "Рекомендованные (суша и шоу)"
        context.user_data['filtered_tours'] = recommended_tours
        
        # Переходим к показу экскурсий
        return await proceed_to_tours(update, context, user_data)

    return CONFIRMATION
    """Обработчик уточняющих ответов пользователя"""
    user_text = update.message.text

    # Проверяем, не это ли исправление после кнопки "✏️ Нет, исправить"
    if context.user_data.get('waiting_for_correction'):
        # Убираем флаг
        del context.user_data['waiting_for_correction']
        
        # Обрабатываем исправление
        return await handle_correction(update, context, user_text)
    
    next_question = context.user_data.get('next_question')
    
    if not next_question:
        # Если нет активного вопроса, значит пользователь просто написал что-то
        # Парсим это как новые данные
        parsed_data, _ = parse_user_response(user_text)
        save_partial_data(context, parsed_data)
        
        # Проверяем, всё ли поняли
        current_data = context.user_data['user_data']
        current_missing = check_missing_points(current_data)
        
        if not current_missing:
            await show_final_confirmation(update, context, current_data)
        else:
            await ask_for_clarification(update, context, current_data, current_missing)
        
        return CONFIRMATION
    
    # Обрабатываем ответ на конкретный вопрос
    user_data = context.user_data.get('user_data', {})
    
    if next_question == 'adults':
        return await handle_adults_clarification(update, context, user_text, user_data)
    elif next_question == 'children':
        return await handle_children_clarification(update, context, user_text, user_data)
    elif next_question == 'pregnant':
        return await handle_pregnant_clarification(update, context, user_text, user_data)
    
    return CONFIRMATION
    
    # Обрабатываем ответ на конкретный вопрос
    user_data = context.user_data.get('user_data', {})
    
    if next_question == 'adults':
        return await handle_adults_clarification(update, context, user_text, user_data)
    elif next_question == 'children':
        return await handle_children_clarification(update, context, user_text, user_data)
    elif next_question == 'pregnant':
        return await handle_pregnant_clarification(update, context, user_text, user_data)
    
    return CONFIRMATION

async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик подтверждения данных"""
    # Перенаправляем либо на обработку кнопок, либо на уточнение
    user_text = update.message.text
    
    # === АНАЛИТИКА ===
    user = update.effective_user
    track_user_session(context, BOT_STAGES['data_collection'])
    logger.log_action(user.id, "confirmed_data", stage=BOT_STAGES['data_collection'])
    context.user_data['last_action'] = 'data_confirmation'
    
    if user_text in ["✅ Да, всё верно", "✏️ Нет, исправить", "🔄 Подобрать из рекомендованных", "🔄 Выбрать другую категорию", "✏️ Изменить параметры", "📋 Показать все", "✏️ Уточнить параметры", "📋 Только ознакомиться с морскими"]:
        return await handle_confirmation_choice(update, context)
    else:
        # Если пользователь ответил что-то непонятное - просим выбрать из кнопок
        await update.message.reply_text(
            "🤔 Не совсем понял ваш ответ. Пожалуйста, выберите один из вариантов выше.",
            reply_markup=make_confirmation_keyboard()
        )
        return CONFIRMATION

async def proceed_to_tours(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data):
    """Переход к показу экскурсий после подтверждения всех данных"""
    
    # Показываем typing indicator - бот ищет экскурсии
    await update.effective_chat.send_chat_action(ChatAction.TYPING)
    await asyncio.sleep(1)  # Имитируем поиск
    
    category = context.user_data.get('category', 'неизвестно')
    category_tours = context.user_data.get('filtered_tours', [])
    user_name = user_data.get('name') or update.effective_user.first_name
    
    # 1. Фильтруем по безопасности
    safe_tours = filter_tours_by_safety(category_tours, user_data)
    context.user_data['safe_tours'] = safe_tours
    
    # 2. ЖЕСТКАЯ приоритизация: ХИТы сначала, потом остальные
    ranked_tours = rank_tours_by_hits_and_priorities(safe_tours, user_data)
    context.user_data['ranked_tours'] = ranked_tours
    
    # 3. Сохраняем текущий offset
    context.user_data['tour_offset'] = 0
    
    if not ranked_tours:
        response = "😔 *Ой-ой! С этими параметрами в \"Море\" не подходит ничего.*\n\n"
        
        # Определяем причины
        is_pregnant = user_data.get('pregnant', False)
        children_ages = user_data.get('children', [])
        has_young_children = any(age < 12 for age in children_ages)
        
        response += "⚡️ *Железное правило:*\n"
        if is_pregnant:
            response += "🤰 Беременность = ❌ **ВСЕ** морские туры\n"
        if has_young_children:
            response += "👶 Дети до года = ❌ **ВСЕ** морские туры\n"
        
        response += "\n🎯 *Лучше выбрать:*\n"
        response += "🏞️ *Суша (обзорные)* — Аватар, смотровые, источники\n"
        response += "🐘 *Суша (семейные)* — слоны, аквапарк, океанариум\n"
        response += "🎭 *Вечерние шоу* — Сиам Нирамит, кабаре\n\n"
        
        response += "👉 *Выбирайте:*"
        
        # Создаем кнопки для выбора
        keyboard = [
            ["🔄 Подобрать из рекомендованных"],
            ["✏️ Уточнить параметры"],
            ["📋 Только ознакомиться с морскими"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        await update.message.reply_text(
            response,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        return CONFIRMATION  # Остаемся в состоянии подтверждения для обработки кнопок
    
    # Если экскурсии найдены - показываем их с ЖЕСТКОЙ приоритизацией ХИТов
    hits = [t for t in ranked_tours if "ХИТ" in t.get("Название", "")]
    regular = [t for t in ranked_tours if "ХИТ" not in t.get("Название", "")]
    
    response = f"🎉 Отлично! Подобрал для вас лучшие варианты в категории *{category}*\n"
    
    if hits:
        response += f"\n🏆 *ХИТы* ({len(hits)})\n"
        response += "─" * 40 + "\n"
        for i, tour in enumerate(hits[:3], 1):
            response += format_tour_card_compact(tour, i)
            response += "\n"
        if len(hits) > 3:
            response += f"\n_... и ещё {len(hits) - 3} вариантов_\n"
    
    if regular:
        response += f"\n📋 *Также есть* ({len(regular)})\n"
        response += "─" * 40 + "\n"
        for i, tour in enumerate(regular[:3], 1):
            response += format_tour_card_compact(tour, i)
            response += "\n"
    
    response += "\n💡 Нажимайте на любой тур для полного описания!"
    
    await update.message.reply_text(
        response,
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )
    
    # Показываем клавиатуру с экскурсиями
    await update.message.reply_text(
        "Выберите экскурсию:",
        reply_markup=make_tours_keyboard(ranked_tours, 0, 5)
    )
    
    return TOUR_DETAILS

async def handle_tour_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора конкретной экскурсии"""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data

# === АНАЛИТИКА: ПРОСМОТР ЭКСКУРСИИ ===
    user = query.from_user
    track_user_session(context, BOT_STAGES['tour_details'])
    logger.log_action(user.id, "viewed_tour", stage=BOT_STAGES['tour_details'])
    context.user_data['last_action'] = 'tour_view'
    # === КОНЕЦ АНАЛИТИКИ ===
    
    if callback_data.startswith("tour_"):
        # Пользователь выбрал конкретную экскурсию
        tour_index = int(callback_data.split("_")[1])
        ranked_tours = context.user_data.get('ranked_tours', [])
        
        if tour_index < len(ranked_tours):
            tour = ranked_tours[tour_index]
            
            # ДОБАВЛЯЕМ ПОДСКАЗКУ ПЕРЕД ОПИСАНИЕМ
            tip_text = f"💡 *Совет:* Если у вас есть вопросы по экскурсии, просто спросите!\n\n"
            
            # ИСПОЛЬЗУЕМ НОВОЕ ФОРМАТИРОВАНИЕ В СТИЛЕ АЛЕКСА
            description = tip_text + format_tour_description_alex_style(tour)
            
            # Создаем кнопки для навигации
            keyboard = [
                [InlineKeyboardButton("📋 Дополнительная информация", callback_data=f"more_info_{tour_index}")],
                [InlineKeyboardButton("🤔 Задать вопрос", callback_data="ask_question")],
                [InlineKeyboardButton("💳 Забронировать", callback_data=f"book_{tour_index}")],
                [InlineKeyboardButton("← К списку экскурсий", callback_data="back_to_list_0")],
                [InlineKeyboardButton("🔄 Выбрать другую категорию", callback_data="change_category")]
            ]
            
            await query.edit_message_text(
                text=description,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard),
                disable_web_page_preview=False  # Разрешаем превью ссылок
            )
    
    elif callback_data.startswith("more_info_"):
        # Пользователь хочет дополнительную информацию
        tour_index = int(callback_data.split("_")[2])
        ranked_tours = context.user_data.get('ranked_tours', [])
        
        if tour_index < len(ranked_tours):
            tour = ranked_tours[tour_index]
            additional_info = get_tour_additional_info(tour)
            
            # Кнопки для возврата
            keyboard = [
                [InlineKeyboardButton("← Назад к описанию", callback_data=f"tour_{tour_index}")],
                [InlineKeyboardButton("← К списку экскурсий", callback_data="back_to_list_0")]
            ]
            
            await query.edit_message_text(
                text=additional_info,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    
    elif callback_data.startswith("prev_") or callback_data.startswith("next_"):
        # Навигация по списку экскурсий
        offset = int(callback_data.split("_")[1])
        ranked_tours = context.user_data.get('ranked_tours', [])
        
        context.user_data['tour_offset'] = offset
        
        # Обновляем список
        await query.edit_message_reply_markup(
            reply_markup=make_tours_keyboard(ranked_tours, offset, 3)
        )
    
    elif callback_data == "back_to_list_0":
        # Возврат к списку экскурсий
        ranked_tours = context.user_data.get('ranked_tours', [])
        offset = context.user_data.get('tour_offset', 0)
        
        await query.edit_message_text(
            text=f"📋 *Доступные экскурсии ({len(ranked_tours)} вариантов):*",
            parse_mode='Markdown',
            reply_markup=make_tours_keyboard(ranked_tours, offset, 3)
        )
    
    elif callback_data == "change_category":
        # Возврат к выбору категории
        await query.edit_message_text(
            text="🔄 Возвращаюсь к выбору категории...",
            parse_mode='Markdown'
        )
        await query.message.reply_text(
            "Выберите категорию экскурсий:",
            reply_markup=make_category_keyboard()
        )
        return CATEGORY

    elif callback_data == "ask_question":
        # Пользователь нажал "Задать вопрос"
        await query.message.reply_text(
            "🤔 **Выберите тему вопроса:**\n\nИли напишите свой вопрос — я передам менеджеру!",
            parse_mode='Markdown',
            reply_markup=make_question_keyboard()
        )
        return QUESTION
    
    elif callback_data.startswith("book_"):
        # Пользователь хочет забронировать экскурсию
        tour_index = int(callback_data.split("_")[1])
        ranked_tours = context.user_data.get('ranked_tours', [])
        
        if tour_index < len(ranked_tours):
            tour = ranked_tours[tour_index]
            user_data = context.user_data.get('user_data', {})
            
            # Проверяем соответствие ограничений
            restriction_check = check_tour_restrictions(tour, user_data)
            if restriction_check:
                # Есть ограничения - показываем сообщение и предлагаем альтернативы
                await query.message.reply_text(
                    restriction_check,
                    parse_mode='Markdown',
                    reply_markup=ReplyKeyboardRemove()
                )
                
                # Показываем доступные категории
                await query.message.reply_text(
                    "🎯 *Выберите доступную категорию:*",
                    parse_mode='Markdown',
                    reply_markup=make_category_keyboard()
                )
                return CATEGORY
            
            # Проверяем флаг readonly для морских туров
            if context.user_data.get('sea_readonly'):
                await query.message.reply_text(
                    "❌ *Бронирование недоступно*\n\n"
                    "Эта экскурсия показана только для ознакомления из-за ваших ограничений.\n"
                    "Выберите другую категорию:",
                    parse_mode='Markdown',
                    reply_markup=make_category_keyboard()
                )
                return CATEGORY
            
            # Сохраняем выбранный тур для бронирования
            context.user_data['booking_tour'] = tour
            context.user_data['booking_tour_index'] = tour_index
            
            # Проверяем, есть ли необходимые данные для бронирования
            missing_info = check_booking_requirements(user_data)
            
            if missing_info:
                # Запрашиваем недостающую информацию
                await query.message.reply_text(
                    f"💳 *Бронирование экскурсии: {tour.get('Название', 'Без названия')}*\n\n"
                    f"📝 *Необходимо уточнить:*\n{missing_info}\n\n"
                    "Пожалуйста, укажите эту информацию:",
                    parse_mode='Markdown',
                    reply_markup=ReplyKeyboardRemove()
                )
                return BOOKING
            else:
                # Все данные есть - подтверждаем бронирование
                await confirm_booking(query, context, tour, user_data)
                return BOOKING
    
    return TOUR_DETAILS

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена диалога"""
    await update.message.reply_text(
        "Диалог прерван. Нажмите /start чтобы начать заново.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def show_tours(update: Update, context: ContextTypes.DEFAULT_TYPE):

# === АНАЛИТИКА: ПОКАЗ СПИСКА ЭКСКУРСИЙ ===
    user = update.effective_user
    track_user_session(context, BOT_STAGES['tour_list'])
    logger.log_action(user.id, "viewed_tour_list", stage=BOT_STAGES['tour_list'])
    context.user_data['last_action'] = 'tour_list'
    # === КОНЕЦ АНАЛИТИКИ ===

    """Тестовая команда для просмотра экскурсий"""
    if not TOURS:
        await update.message.reply_text("❌ Данные не загружены")
        return
    
    # Показываем первые 3 экскурсии
    response = "📋 *Список экскурсий (первые 3):*\n\n"
    for i, tour in enumerate(TOURS[:3]):
        name = tour.get("Название", "Без названия")
        price_adult = tour.get("Цена Взр", "?")
        price_child = tour.get("Цена Дет", "?")
        response += f"{i+1}. *{name}*\n"
        response += f"   Взрослый: `{price_adult}฿`, Детский: `{price_child}฿`\n\n"
    
    response += f"Всего в базе: {len(TOURS)} экскурсий"
    await update.message.reply_text(response, parse_mode='Markdown')

async def debug_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для отладки - показывает что бот запомнил"""
    if 'user_data' not in context.user_data:
        await update.message.reply_text("❌ Нет данных о пользователе")
        return

    user_data = context.user_data['user_data']

    response = "🔧 *Отладочная информация:*\n\n"
    response += f"*Взрослые:* {user_data.get('adults', 0)}\n"

    if user_data.get('children'):
        children_count = len(user_data['children'])
        age_texts = [format_age_months(months) for months in user_data['children']]

        if children_count == 1:
            children_text = "1 ребенок"
        elif children_count in [2, 3, 4]:
            children_text = f"{children_count} ребенка"
        else:
            children_text = f"{children_count} детей"

        response += f"*Дети:* {children_text} ({', '.join(age_texts)})\n"
    else:
        response += "*Дети:* Нет\n"

    response += f"*Беременность:* {'Да' if user_data.get('pregnant') else 'Нет'}\n"

    if user_data.get('priorities'):
        response += f"*Приоритеты:* {', '.join(user_data['priorities'])}\n"

    if user_data.get('health_issues'):
        response += f"*Проблемы со здоровьем:* {', '.join(user_data['health_issues'])}\n"

    response += f"\n*Сырой текст:* {user_data.get('raw_text', 'N/A')}"

    await update.message.reply_text(response, parse_mode='Markdown')


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистить контекст пользователя - ТОЛЬКО ДЛЯ АДМИНОВ"""
    user_id = update.effective_user.id
    
    # Проверка на администратора
    ADMINS = [7966971037]  # Ваш Telegram ID
    
    if user_id not in ADMINS:
        await update.message.reply_text("❌ Эта команда только для администраторов")
        return
    
    # Получаем ID пользователя из аргументов команды
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите ID пользователя: /clear <user_id>")
        return
    
    try:
        target_user_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом")
        return
    
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Удаляем все данные пользователя из аналитики
        cursor.execute("DELETE FROM user_actions WHERE user_id = ?", (target_user_id,))
        cursor.execute("DELETE FROM drop_off_points WHERE user_id = ?", (target_user_id,))
        cursor.execute("DELETE FROM analytics WHERE user_id = ?", (target_user_id,))
        
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Контекст пользователя {target_user_id} очищен")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при очистке: {e}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать расширенную статистику бота с аналитикой - ТОЛЬКО ДЛЯ АДМИНОВ"""
    user_id = update.effective_user.id
    
    # Проверка на администратора (ваш ID)
    ADMINS = [7966971037]  # Ваш Telegram ID
    
    if user_id not in ADMINS:
        await update.message.reply_text("❌ Эта команда только для администраторов")
        return
    
    try:
        # ==================== ОБЩАЯ СТАТИСТИКА ====================
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        response = "📊 РАСШИРЕННАЯ СТАТИСТИКА БОТА АЛЕКСА\n\n"
        
        # 1. БАЗОВАЯ СТАТИСТИКА
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM user_actions WHERE action='started_bot'")
        started_bot = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM user_actions WHERE action='chose_category'")
        chose_category = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM user_actions WHERE action='viewed_tour'")
        viewed_tour = cursor.fetchone()[0] or 0
        
        response += "📈 КОНВЕРСИЯ ПО ЭТАПАМ:\n"
        response += f"• /start: {started_bot} пользователей\n"
        response += f"• Выбор категории: {chose_category} ({(chose_category/started_bot*100 if started_bot > 0 else 0):.1f}% от стартов)\n"
        response += f"• Просмотр экскурсий: {viewed_tour} ({(viewed_tour/started_bot*100 if started_bot > 0 else 0):.1f}% от стартов)\n\n"
        
        # 2. ТОЧКИ УХОДА (DROP-OFFS)
        cursor.execute('''
            SELECT drop_off_stage, COUNT(*) as count 
            FROM drop_off_points 
            GROUP BY drop_off_stage 
            ORDER BY count DESC
        ''')
        drop_offs = cursor.fetchall()
        
        if drop_offs:
            response += "📍 ТОЧКИ УХОДА КЛИЕНТОВ:\n"
            for stage, count in drop_offs[:5]:
                response += f"• {stage}: {count} уходов\n"
            response += "\n"
        
        # 3. САМЫЕ ПОПУЛЯРНЫЕ ЭКСКУРСИИ
        cursor.execute('''
            SELECT tour_name, COUNT(*) as views, AVG(view_time_seconds) as avg_time 
            FROM tour_views 
            WHERE tour_name IS NOT NULL 
            GROUP BY tour_name 
            ORDER BY views DESC 
            LIMIT 5
        ''')
        popular_tours = cursor.fetchall()
        
        if popular_tours:
            response += "🏆 ТОП-5 ЭКСКУРСИЙ:\n"
            for tour_name, views, avg_time in popular_tours:
                avg_min = int(avg_time // 60) if avg_time else 0
                avg_sec = int(avg_time % 60) if avg_time else 0
                response += f"• {tour_name[:30]}: {views} просмотров ({avg_min}м {avg_sec}с)\n"
            response += "\n"
        
        # 4. ЧАСТЫЕ ВОПРОСЫ
        cursor.execute('''
            SELECT question_type, COUNT(*) as count 
            FROM user_questions 
            WHERE question_type IS NOT NULL 
            GROUP BY question_type 
            ORDER BY count DESC 
            LIMIT 5
        ''')
        frequent_questions = cursor.fetchall()
        
        if frequent_questions:
            response += "❓ ЧАСТЫЕ ВОПРОСЫ:\n"
            for q_type, count in frequent_questions:
                response += f"• {q_type}: {count} раз\n"
            response += "\n"
        
        # 5. ОШИБКИ (ТОЛЬКО ЗА ПОСЛЕДНИЕ 7 ДНЕЙ)
        cursor.execute('''
            SELECT error_type, COUNT(*) as count 
            FROM error_logs 
            WHERE timestamp > datetime('now', '-7 days')
            GROUP BY error_type 
            ORDER BY count DESC
        ''')
        recent_errors = cursor.fetchall()
        
        if recent_errors:
            response += "⚠️ ОШИБКИ (7 ДНЕЙ):\n"
            for err_type, count in recent_errors:
                response += f"• {err_type}: {count}\n"
            response += "\n"
        
        # 6. ВРЕМЯ СЕССИЙ
        cursor.execute('SELECT AVG(session_duration) FROM drop_off_points WHERE session_duration > 0')
        avg_session = cursor.fetchone()[0]
        
        if avg_session:
            avg_min = int(avg_session // 60)
            avg_sec = int(avg_session % 60)
            response += f"⏱️ Среднее время в боте: {avg_min} минут {avg_sec} секунд\n\n"
        
        # 7. АКТИВНОСТЬ СЕГОДНЯ
        cursor.execute("SELECT COUNT(*) FROM user_actions WHERE DATE(timestamp) = DATE('now')")
        today_actions = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM user_actions WHERE DATE(timestamp) = DATE('now')")
        today_users = cursor.fetchone()[0]
        
        response += f"🚀 СЕГОДНЯ: {today_users} пользователей, {today_actions} действий\n"
        
        conn.close()
        
        # Добавляем подсказки для администратора
        response += "\n" + "="*40 + "\n"
        response += "📋 КОМАНДЫ АНАЛИТИКИ:\n"
        response += "/stats_drops - Детали уходов\n"
        response += "/stats_errors - Все ошибки\n"
        response += "/stats_questions - Все вопросы\n"
        response += "/stats_tours - Все экскурсии\n"
        
        await update.message.reply_text(response)
        
    except Exception as e:
        print(f"❌ Ошибка статистики: {e}")
        import traceback
        traceback.print_exc()
        
        # Логируем ошибку статистики
        logger.log_error(
            error_type=ERROR_TYPES['db_error'],
            error_message=f"stats_command error: {str(e)}",
            user_id=user_id,
            bot_state='stats',
            user_action='stats_command'
        )
        
        await update.message.reply_text("❌ Ошибка получения статистики. Данные логированы.")

# ==================== ДОПОЛНИТЕЛЬНЫЕ КОМАНДЫ АНАЛИТИКИ ====================

async def stats_drops_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детальная статистика по точкам ухода"""
    user_id = update.effective_user.id
    ADMINS = [7966971037]
    
    if user_id not in ADMINS:
        await update.message.reply_text("❌ Только для администраторов")
        return
    
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT drop_off_stage, COUNT(*) as count, 
                   AVG(session_duration) as avg_time,
                   MIN(timestamp) as first_occurrence,
                   MAX(timestamp) as last_occurrence
            FROM drop_off_points 
            GROUP BY drop_off_stage 
            ORDER BY count DESC
        ''')
        
        drops = cursor.fetchall()
        conn.close()
        
        response = "📍 ДЕТАЛЬНАЯ СТАТИСТИКА УХОДОВ:\n\n"
        
        for stage, count, avg_time, first, last in drops:
            avg_min = int(avg_time // 60) if avg_time else 0
            avg_sec = int(avg_time % 60) if avg_time else 0
            response += f"🎯 {stage}:\n"
            response += f"   • Уходов: {count}\n"
            response += f"   • Среднее время: {avg_min}м {avg_sec}с\n"
            response += f"   • Первый: {first[:10] if first else 'N/A'}\n"
            response += f"   • Последний: {last[:10] if last else 'N/A'}\n\n"
        
        if not drops:
            response = "📭 Данных об уходах пока нет"
        
        await update.message.reply_text(response)
        
    except Exception as e:
        logger.log_error(
            error_type=ERROR_TYPES['db_error'],
            error_message=f"stats_drops error: {str(e)}",
            user_id=user_id
        )
        await update.message.reply_text("❌ Ошибка получения данных об уходах")

# Аналогично можно добавить:
# stats_errors_command, stats_questions_command, stats_tours_command

# ==================== КНОПКА "ЗАДАТЬ ВОПРОС" (ШАГ 5) ====================
def make_question_keyboard():
    """Клавиатура для вопросов"""
    keyboard = [
        ["🤔 Вопрос про экскурсию"],
        ["💰 Вопрос про оплату"],
        ["👶 Вопрос про детей"],
        ["🚗 Вопрос про трансфер"],
        ["📅 Вопрос про даты"],
        ["⬅️ Назад к выбору"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

FAQ_ANSWERS = {
    "🤔 Вопрос про экскурсию": """
❓ **Частые вопросы об экскурсиях:**

• Можно ли поменять дату? — Да, если есть места.
• Плохая погода — экскурсия отменяется? — Только при штормовом предупреждении.
• Можно ли взять свою маску/ласты? — Конечно, это даже лучше!
• Что включено в стоимость? — Только указанное в описании.

*Обязательно ознакомьтесь с полными условиями перед бронированием:* 
👉 [Правила бронирования](https://goldenkeytours.com/booking-and-cancellation-conditions)
""",

    "💰 Вопрос про оплату": """
💸 **Основное об оплате и возврате:**

• **Отмена за 24+ часа до тура** → возвращается **50%**
• **Отмена менее чем за 24 часа** → возврата нет
• **Болезнь** → возврат **только при справке из международного госпиталя до 16:00**
• **Авиатуры/индивидуальные туры** → возврата нет

*Это краткая сводка. Всё остальное в полных правилах:*
👉 [Правила бронирования](https://goldenkeytours.com/booking-and-cancellation-conditions)
""",

    "👶 Вопрос про детей": """
👨‍👩‍👧‍👦 **Дети на экскурсиях:**

• **Морские экскурсии** — детям до 1 года запрещены по правилам безопасности
• **Беременным** — все морские экскурсии запрещены
• **Дети от 1 года** — большинство экскурсий доступны
• **Специальные детские программы** — есть в категориях "Суша (семейные)"

**Полезная информация:**
• На большинстве экскурсий дети до 4 лет бесплатно (проверяйте в описании)
• Для детей от 4 лет — детский тариф
• Рекомендуем брать удобную одежду и головные уборы
• На морских экскурсиях — спасательные жилеты для всех детей

**Если ребенок заболел:**
• Возврат возможен только при справке из международного госпиталя
• Справка должна быть предоставлена до 16:00 дня перед экскурсией
• Возврат на ребенка + одного родителя

👉 *Все детали в* [Правилах бронирования](https://goldenkeytours.com/booking-and-cancellation-conditions)
""",

    "🚗 Вопрос про трансфер": """
🚐 **Про трансфер:**

• Чаще всего бесплатно с пляжей Ката, Карон, Патонг
• Для других районов возможна доплата (уточняйте)
• Время ожидания водителя может быть до 1 часа

*Точную стоимость трансфера из вашего отеля уточнит менеджер после выбора экскурсии.*
""",

    "📅 Вопрос про даты": """
📆 **Даты и расписание:**

• **Большинство экскурсий** — ежедневно
• **Некоторые** — по конкретным дням недели (информация есть в "Дополнительной информации" к каждой экскурсии)
• **VIP-туры и приватные яхты** — обычно "По запросу"

*Укажите желаемую дату — менеджер проверит доступность после согласования экскурсии.*
""",
}

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):

# === ЭФФЕКТ САЛЮТА НА СООБЩЕНИИ КЛИЕНТА ===
    try:
        # Салют - визуальная обратная связь что сообщение получено
        await update.effective_chat.send_chat_action(ChatAction.TYPING)
    except:
        pass

# === АНАЛИТИКА: ВОПРОС FAQ ===
    user = update.effective_user
    track_user_session(context, BOT_STAGES['faq'])
    logger.log_action(user.id, "asked_question", stage=BOT_STAGES['faq'])
    context.user_data['last_action'] = 'faq_question'
    # === КОНЕЦ АНАЛИТИКИ ===

    """Обработчик вопросов пользователя с поиском по ключевым словам"""
    user = update.effective_user
    question_text = update.message.text.lower()  # переводим в нижний регистр для поиска
    
    log_user_action(user.id, "ask_question", question_text)
    
    # 1. Если нажали "Назад к выбору"
    if "назад к выбору" in question_text.lower():
            
        await update.message.reply_text(
            "Возвращаюсь к выбору экскурсий...",
            reply_markup=ReplyKeyboardRemove()
        )
        
        ranked_tours = context.user_data.get('ranked_tours', [])
        offset = context.user_data.get('tour_offset', 0)
        
        await update.message.reply_text(
            f"📋 *Доступные экскурсии ({len(ranked_tours)} вариантов):*",
            parse_mode='Markdown',
            reply_markup=make_tours_keyboard(ranked_tours, offset, 5)
        )
        return TOUR_DETAILS
    
    # 2. Если нажали на кнопку из FAQ
    elif question_text in [q.lower() for q in FAQ_ANSWERS.keys()]:
            
        # Находим оригинальный ключ (с заглавными буквами и эмодзи)
        for key in FAQ_ANSWERS.keys():
            if key.lower() == question_text:
                answer = FAQ_ANSWERS[key]
                await update.message.reply_text(
                    answer,
                    parse_mode='Markdown',
                    reply_markup=make_question_keyboard()
                )
                return QUESTION
    
    # 3. ПОИСК ПО КЛЮЧЕВЫМ СЛОВАМ
    elif any(word in question_text for word in ['заболе', 'температур', 'плохо себя чувств', 'просту', 'болен', 'грипп', 'орви']):
            
        await update.message.reply_text(
            answer,
            parse_mode='Markdown',
            reply_markup=make_question_keyboard()
        )
        return QUESTION
    
    elif any(word in question_text for word in ['вернут', 'отмен', 'передума', 'не поеду', 'возврат деньг', 'верните', 'отказаться', 'передумываю']):
            
        await update.message.reply_text(
            answer,
            parse_mode='Markdown',
            reply_markup=make_question_keyboard()
        )
        return QUESTION
    
    elif any(word in question_text for word in ['шторм', 'погод', 'дожд', 'отменят', 'ливень', 'ураган', 'тайфун', 'непогода']):
            
        await update.message.reply_text(
            answer,
            parse_mode='Markdown',
            reply_markup=make_question_keyboard()
        )
        return QUESTION
    
    elif any(word in question_text for word in ['доплат', 'трансфер дорог', 'дорого трансфер', 'оплата трансфер']):
        await update.message.reply_text(
            answer,
            parse_mode='Markdown',
            reply_markup=make_question_keyboard()
        )
        return QUESTION
    
    # 4. Если вопрос не распознан - используем DeepSeek
    else:
        # Получаем данные выбранного тура, если есть
        selected_tour = context.user_data.get('selected_tour')
        tour_data = None
        if selected_tour:
            # Ищем тур по ID или названию
            for tour in TOURS:
                if tour.get('ID') == selected_tour or tour.get('Название') == selected_tour:
                    tour_data = tour
                    break

        # Получаем контекст пользователя
        user_data = context.user_data.get('user_data', {})
        context_info = f"Состав группы: {user_data.get('adults', 0)} взрослых"
        if user_data.get('children'):
            context_info += f", {len(user_data['children'])} детей"
        if user_data.get('pregnant'):
            context_info += ", беременная"

        # Показываем typing indicator - бот "думает"
        await update.effective_chat.send_chat_action(ChatAction.TYPING)
        await asyncio.sleep(1.5)  # Даем время на "размышление"

        # Генерируем ответ с DeepSeek
        deepseek_answer = generate_deepseek_response(
            user_query=update.message.text,
            tour_data=tour_data,
            context_info=context_info,
            user_name=update.effective_user.first_name
        )

        # Красиво форматируем ответ
        deepseek_answer = format_deepseek_answer(deepseek_answer)

        await update.message.reply_text(
            deepseek_answer,
            parse_mode='Markdown',
            reply_markup=make_question_keyboard()
        )
        
        # ДОБАВЛЯЕМ ПОДСКАЗКУ ПОСЛЕ ОТВЕТА
        await update.message.reply_text(
            "💡 *Совет:* Можете задать ещё вопросы или вернуться к выбору экскурсий",
            parse_mode='Markdown'
        )
        
        return QUESTION

def check_booking_requirements(user_data):
    """Проверяет, есть ли все необходимые данные для бронирования"""
    missing = []
    
    # Отель теперь опционален - будет запрошен отдельно
    # if not user_data.get('hotel'):
    #     missing.append("🏨 *Название отеля* (обязательно для транспорта)")
    
    if not user_data.get('phone'):
        missing.append("📱 *Номер телефона*")
    
    # Дата не обязательна, но желательна
    # if not user_data.get('booking_date'):
    #     missing.append("📅 *Желаемая дата*")
    
    return "\n".join(f"• {item}" for item in missing)

def check_tour_restrictions(tour, user_data):
    """Проверяет соответствие тура ограничениям пользователя"""
    is_pregnant = user_data.get('pregnant', False)
    children_ages = user_data.get('children', [])
    
    tags = tour.get("Теги (Безопасность)", "").lower()
    
    restrictions = []
    
    # === 1. ПРОВЕРКА ДЛЯ БЕРЕМЕННЫХ ===
    if is_pregnant:
        if "#нельзя_беременным" in tags:
            restrictions.append("🤰 Беременным запрещены все морские экскурсии")
        elif "#можно_беременным" not in tags and "#можно_всем" not in tags:
            # Если нет явного разрешения для беременных - по умолчанию нельзя
            restrictions.append("🤰 Беременным не рекомендуются морские экскурсии")
    
    # === 2. ПРОВЕРКА ВОЗРАСТА ДЕТЕЙ ===
    if children_ages:
        # Проверяем каждого ребенка на соответствие возрастным ограничениям
        for age_months in children_ages:
            # Если ребенок до 1 года (12 месяцев)
            if age_months < 12:
                if "#дети_от_1_года" in tags or "#от_18_лет" in tags or "#дети_от_2_лет" in tags or \
                   "#дети_от_3_лет" in tags or "#дети_от_4_лет" in tags or "#дети_от_5_лет" in tags or \
                   "#дети_от_6_лет" in tags or "#дети_от_7_лет" in tags or "#дети_от_8_лет" in tags or \
                   "#дети_от_9_лет" in tags or "#дети_от_10_лет" in tags or "#дети_от_11_лет" in tags or \
                   "#дети_от_12_лет" in tags or "#дети_от_13_лет" in tags or "#дети_от_14_лет" in tags or \
                   "#дети_от_15_лет" in tags or "#дети_от_16_лет" in tags or "#дети_от_17_лет" in tags:
                    restrictions.append(f"👶 Детям до 1 года запрещены активные и морские экскурсии")
    
    if restrictions:
        response = "❌ *Эта экскурсия не подходит для вашей группы:*\n\n"
        response += "\n".join(f"• {r}" for r in restrictions)
        response += "\n\n🎯 *Рекомендую выбрать другие категории:*"
        return response
    
    return None
    """Проверяет, есть ли все необходимые данные для бронирования"""
    missing = []
    
    if not user_data.get('hotel'):
        missing.append("🏨 *Название отеля* (обязательно для транспорта)")
    
    if not user_data.get('phone'):
        missing.append("📱 *Номер телефона*")
    
    # Дата не обязательна, но желательна
    # if not user_data.get('booking_date'):
    #     missing.append("📅 *Желаемая дата*")
    
    return "\n".join(f"• {item}" for item in missing)

async def confirm_booking(query, context, tour, user_data):
    """Подтверждает бронирование и отправляет менеджеру"""
    user = query.from_user
    
    # Формируем сводку для менеджера
    manager_message = format_booking_summary(user, tour, user_data)
    
    # Отправляем менеджеру
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=manager_message,
            parse_mode='Markdown'
        )
        
        # Подтверждаем пользователю
        await query.message.reply_text(
            "✅ *Бронирование отправлено менеджеру!*\n\n"
            "📞 Менеджер свяжется с вами в ближайшее время для подтверждения деталей.\n\n"
            "🤝 Спасибо за выбор GoldenKeyTours!",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup([["🔄 Выбрать другую экскурсию"], ["/start"]], resize_keyboard=True)
        )
        
        # Логируем бронирование
        logger.log_action(user.id, "booking_completed", tour_id=tour.get('ID'), category=context.user_data.get('category'))
        
    except Exception as e:
        await query.message.reply_text(
            "❌ *Ошибка при отправке бронирования*\n\n"
            "Попробуйте позже или свяжитесь с менеджером напрямую.",
            parse_mode='Markdown'
        )
        print(f"Ошибка отправки бронирования: {e}")

def format_booking_summary(user, tour, user_data):
    """Форматирует сводку бронирования для менеджера"""
    # Имя клиента
    client_name = user_data.get('name') or user.first_name or "Не указано"
    
    # Состав группы
    adults = user_data.get('adults', 0)
    children_info = []
    if user_data.get('children'):
        for age_months in user_data['children']:
            age_str = format_age_months(age_months)
            children_info.append(age_str)
    
    children_text = f"{len(children_info)} ({', '.join(children_info)})" if children_info else "нет"
    
    pregnancy = "да" if user_data.get('pregnant') else "нет"
    
    # Экскурсия
    tour_name = tour.get('Название', 'Без названия')
    
    # Дата
    booking_date = user_data.get('booking_date', 'Не указана')
    
    # Отель
    hotel = user_data.get('hotel', 'Не указан')
    
    # Телефон
    phone = user_data.get('phone', 'Не указан')
    
    summary = f"""💳 *НОВОЕ БРОНИРОВАНИЕ*

👤 *Клиент:* {client_name} (Telegram: @{user.username or 'нет'})
📞 *Телефон:* {phone}

👥 *Состав группы:*
• Взрослых: {adults}
• Детей: {children_text}
• Беременность: {pregnancy}

🎯 *Экскурсия:* {tour_name}
📅 *Желаемая дата:* {booking_date}
🏨 *Отель:* {hotel}

💰 *Цены:*
• Взрослый: {tour.get('Цена Взр', '?')} THB
• Детский: {tour.get('Цена Дет', '?')} THB

🔗 *Ссылка:* {tour.get('Ссылка', 'Нет')}

⚠️ *Важная информация:* {tour.get('Важная информация', 'Нет')}"""
    
    return summary

async def handle_booking_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод данных для бронирования"""
    user_text = update.message.text
    user_data = context.user_data.get('user_data', {})
    tour = context.user_data.get('booking_tour')
    
    # === АНАЛИТИКА ===
    user = update.effective_user
    track_user_session(context, BOT_STAGES['booking'])
    logger.log_action(user.id, "booking_input", stage=BOT_STAGES['booking'])
    context.user_data['last_action'] = 'booking_input'
    # === КОНЕЦ АНАЛИТИКИ ===
    
    # Парсим введенные данные
    parsed_data = parse_booking_info(user_text)
    
    # Обновляем user_data
    user_data.update(parsed_data)
    context.user_data['user_data'] = user_data
    
    # Проверяем, все ли собрали
    missing_info = check_booking_requirements(user_data)
    
    if missing_info:
        await update.message.reply_text(
            f"📝 *Ещё необходимо:*\n{missing_info}\n\n"
            "Пожалуйста, укажите:",
            parse_mode='Markdown'
        )
        return BOOKING
    else:
        # Все обязательные данные есть - проверяем отель
        if user_data.get('hotel'):
            # Отель уже указан - подтверждаем бронирование
            await confirm_booking_via_message(update, context, tour, user_data)
            return ConversationHandler.END
        else:
            # Отель не указан - спрашиваем опционально
            await update.message.reply_text(
                "🏨 *Хотите указать название отеля?*\n\n"
                "Это поможет менеджеру организовать трансфер.\n\n"
                "📝 *Варианты ответа:*\n"
                "• Укажите название отеля\n"
                "• Напишите 'нет' или 'пропустить'\n"
                "• Или просто нажмите 'Продолжить без отеля'",
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardMarkup([
                    ["🏨 Указать отель", "➡️ Продолжить без отеля"]
                ], resize_keyboard=True)
            )
            return BOOKING_HOTEL

async def handle_booking_hotel_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает опциональный ввод отеля для бронирования"""
    user_text = update.message.text.strip()
    user_data = context.user_data.get('user_data', {})
    tour = context.user_data.get('booking_tour')
    
    # === АНАЛИТИКА ===
    user = update.effective_user
    track_user_session(context, BOT_STAGES['booking'])
    logger.log_action(user.id, "booking_hotel_input", stage=BOT_STAGES['booking'])
    context.user_data['last_action'] = 'booking_hotel_input'
    # === КОНЕЦ АНАЛИТИКИ ===
    
    # Проверяем ответ пользователя
    skip_keywords = ['нет', 'пропустить', 'продолжить без отеля', '➡️ продолжить без отеля']
    
    if user_text.lower() in skip_keywords or user_text == "➡️ Продолжить без отеля":
        # Пользователь не хочет указывать отель
        await update.message.reply_text(
            "✅ *Понятно, продолжаем без указания отеля.*\n\n"
            "Менеджер свяжется для уточнения деталей трансфера.",
            parse_mode='Markdown'
        )
    elif user_text == "🏨 Указать отель":
        # Просим ввести отель
        await update.message.reply_text(
            "🏨 *Укажите название вашего отеля:*\n\n"
            "Например: Patong Beach Hotel или просто 'Patong Beach'",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        return BOOKING_HOTEL
    else:
        # Пользователь ввел название отеля
        user_data['hotel'] = user_text.title()
        context.user_data['user_data'] = user_data
        
        await update.message.reply_text(
            f"✅ *Отель сохранен:* {user_data['hotel']}\n\n"
            "Теперь все данные готовы для бронирования.",
            parse_mode='Markdown'
        )
    
    # Подтверждаем бронирование
    await confirm_booking_via_message(update, context, tour, user_data)
    return ConversationHandler.END

def parse_booking_info(text):
    """Парсит информацию для бронирования из текста"""
    data = {}
    text_lower = text.lower()
    
    # Ищем отель
    hotel_keywords = ['отель', 'гостиница', 'hotel', 'resort']
    for keyword in hotel_keywords:
        if keyword in text_lower:
            # Простой парсинг - берем текст после ключевого слова
            parts = text_lower.split(keyword, 1)
            if len(parts) > 1:
                hotel = parts[1].strip()
                # Очищаем от лишнего
                hotel = hotel.split('\n')[0].split(',')[0].strip()
                if hotel:
                    data['hotel'] = hotel.title()
                    break
    
    # Ищем телефон
    import re
    phone_match = re.search(r'(\+?[\d\s\-\(\)]{7,})', text)
    if phone_match:
        data['phone'] = phone_match.group(1).strip()
    
    # Ищем дату (простой поиск)
    date_keywords = ['дата', 'число', 'date']
    for keyword in date_keywords:
        if keyword in text_lower:
            # Ищем паттерны дат
            date_patterns = [
                r'(\d{1,2}[\.\-\/]\d{1,2}[\.\-\/]\d{2,4})',  # 25.12.2025
                r'(\d{1,2}\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4})'  # 25 декабря 2025
            ]
            for pattern in date_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    data['booking_date'] = match.group(1)
                    break
            break
    
    return data

# === ИНТЕГРАЦИЯ DEEPSEEK ===
def generate_deepseek_response(user_query, tour_data=None, context_info=None, user_name=None):
    """
    Генерирует ответ с помощью DeepSeek Chat.
    Использует только предоставленные данные из прайса.
    """
    if not DEEPSEEK_API_KEY:
        return "Извините, функция ИИ временно недоступна. Попробуйте позже."

    try:
        client = openai.OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com/v1"  # Официальный endpoint DeepSeek
        )

        # Системный промпт для роли профессионального помощника
        user_greeting = f"Ты общаешься с пользователем {user_name}." if user_name else "Ты общаешься с пользователем."
        system_prompt = f"""Ты - профессиональный помощник по экскурсиям в Пhuket от компании GoldenKeyTours.
{user_greeting}

Твоя ГЛАВНАЯ РОЛЬ:
✅ Помогать клиентам найти идеальную экскурсию
✅ Быть честным и информативным
✅ Уважать время и бюджет клиента
✅ Рекомендовать только реальные туры из прайса

🔴 АБСОЛЮТНО ЗАПРЕЩЕНО:
- НЕ выдумывай туры, которых нет в базе
- НЕ меняй цены или создавай несуществующие ссылки
- НЕ пытайся скрыть что это бот или систем
- НЕ давай советы которые противоречат CSV данным

ТОН И СТИЛЬ:
- Профессиональный, но дружелюбный
- Честный и прямой ("Вот что нашел..." вместо "Я рекомендую...")
- Уважение к выбору клиента (не уговаривай)
- Легкий юмор только когда в тему
- Максимум 100-120 слов
- Раздели на 2-3 коротких абзаца

ФОРМУЛА ОТВЕТА на поиск туров:
1️⃣ Подтверди что нашел туры ("По вашему запросу нашел X туров...")
2️⃣ Краткое объяснение почему это интересно (1-2 предложения из описания)
3️⃣ Предложи выбрать ("Вот полный список, выбирайте что нравится")
4️⃣ НЕ говори "купите" - говори "смотрите, изучайте"

ПРИМЕРЫ ЧЕСТНОГО ОБЩЕНИЯ:
❌ "Слоны? Это наша гордость! Вот топ-варианты!"
✅ "По вашему запросу нашел 8 туров со слонами. 
Самые популярные — 'Катание со слонами' (1200 THB) и 'Кормление' (900 THB).
Смотрите описания и выбирайте что по вкусу:"

❌ "Рыбалка? Обязательно попробуйте, это шикарно!"
✅ "Есть 3 вида рыбалки — от спокойной на рассвете до экстримального Big Game.
Все с разными ценами. Вот варианты:"

ГЛАВНОЕ: Клиент должен ЧУВСТВОВАТЬ что ему помогают честно, 
а не продают любой ценой. Это строит доверие и повышает конверсию.
"""

        # Формируем контекст с данными тура
        tour_context = ""
        if tour_data:
            tour_name = tour_data.get('Название', 'Не указано')
            tour_price_adult = tour_data.get('Цена Взр', 'Не указана')
            tour_price_child = tour_data.get('Цена Дет', 'Не указана')
            tour_desc = tour_data.get('Описание (Витрина)', 'Не указано')
            tour_review = tour_data.get('Честный обзор', 'Не указано')
            tour_info = tour_data.get('Важная информация', 'Не указано')
            tour_link = tour_data.get('Ссылка', 'Не указана')
            tour_tags = tour_data.get('Теги (Безопасность)', 'Не указаны')
            
            tour_context = f"""

ДАННЫЕ О ТУРЕ (используй ТОЛЬКО эти факты):
Название: {tour_name}
Цена взрослый: {tour_price_adult} THB
Цена детский: {tour_price_child} THB
Описание: {tour_desc}
Честный обзор: {tour_review}
Важная информация: {tour_info}
Ссылка: {tour_link}
Теги безопасности: {tour_tags}"""

        # Дополнительный контекст
        extra_context = ""
        if context_info:
            extra_context = f"\n\nКОНТЕКСТ: {context_info}"

        # Строим сообщения - устанавливаем явно UTF-8
        messages = [
            {"role": "system", "content": system_prompt + tour_context + extra_context},
            {"role": "user", "content": user_query}
        ]

        # Вызываем API с оптимальными параметрами
        response = client.chat.completions.create(
            model="deepseek-chat",        # Модель: DeepSeek Chat (v3+)
            messages=messages,
            max_tokens=1024,              # Максимум токенов для ответа
            temperature=0.8,              # 0.8 для естественного разговора
            top_p=0.95,                   # Nucleus sampling для разнообразия
            frequency_penalty=0.5         # Избегаем повторений
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Ошибка DeepSeek API: {error_msg}")
        
        # Логируем детали ошибки для диагностики
        if "401" in error_msg or "Unauthorized" in error_msg or "Invalid API key" in error_msg:
            return "❌ Ошибка авторизации DeepSeek. Проверьте API ключ в .env файле."
        elif "429" in error_msg or "rate_limit" in error_msg:
            return "⏳ Слишком много запросов. Подождите немного и попробуйте снова"
        elif "402" in error_msg or "insufficient_quota" in error_msg or "balance" in error_msg.lower():
            return "💳 Недостаточно средств на счете DeepSeek. Пополните баланс на deepseek.com"
        elif "404" in error_msg or "not found" in error_msg.lower():
            return "❌ Модель 'deepseek-chat' не найдена. Проверьте настройки API."
        elif "timeout" in error_msg.lower() or "connection" in error_msg.lower():
            return "⚠️ Проблема с подключением к DeepSeek. Проверьте интернет."
        else:
            # Общая ошибка
            return "Извините, произошла ошибка при обработке вашего вопроса. Попробуйте переформулировать его."

# === КОНЕЦ ИНТЕГРАЦИИ DEEPSEEK ===

async def confirm_booking_via_message(update, context, tour, user_data):
    """Подтверждает бронирование через обычное сообщение (не callback)"""
    user = update.effective_user
    
    # Формируем сводку для менеджера
    manager_message = format_booking_summary(user, tour, user_data)
    
    # Отправляем менеджеру
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=manager_message,
            parse_mode='Markdown'
        )
        
        # Подтверждаем пользователю
        await update.message.reply_text(
            "✅ *Бронирование отправлено менеджеру!*\n\n"
            "📞 Менеджер свяжется с вами в ближайшее время для подтверждения деталей.\n\n"
            "🤝 Спасибо за выбор GoldenKeyTours!",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup([["🔄 Выбрать другую экскурсию"], ["/start"]], resize_keyboard=True)
        )
        
        # Логируем бронирование
        logger.log_action(user.id, "booking_completed", tour_id=tour.get('ID'), category=context.user_data.get('category'))
        
    except Exception as e:
        await update.message.reply_text(
            "❌ *Ошибка при отправке бронирования*\n\n"
            "Попробуйте позже или свяжитесь с менеджером напрямую.",
            parse_mode='Markdown'
        )
        print(f"Ошибка отправки бронирования: {e}")

# ==================== ЗАПУСК БОТА ====================
def main():
    """Запуск бота"""
    print("🚀 Запуск бота Алекса...")
    print(f"📊 Загружено экскурсий: {len(TOURS)}")
    
    categories = get_categories()
    print(f"📂 Категории: {categories}")
    
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).connect_timeout(30.0).read_timeout(30.0).build()
    
# Настройка диалога
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CATEGORY: [
                MessageHandler(
                    filters.Regex(r'^(🌊 Продолжить с Морем.*|🔄 Выбрать другую категорию)$'), 
                    handle_category_choice
                ),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category)
            ],
            QUALIFICATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_qualification)
            ],
            CONFIRMATION: [  # ДОБАВЛЯЕМ ОБА ОБРАБОТЧИКА
                MessageHandler(
                    filters.Regex(r'^(✅ Да, всё верно|✏️ Нет, исправить)$'), 
                    handle_confirmation
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, 
                    handle_confirmation
                )
            ],
            TOUR_DETAILS: [
                CallbackQueryHandler(handle_tour_selection)
            ],
            QUESTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question)
            ],
            BOOKING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_booking_input)
            ],
            BOOKING_HOTEL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_booking_hotel_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Добавляем обработчики
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("tours", show_tours))
    application.add_handler(CommandHandler("debug", debug_info))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("clear", clear_command))
    
    print("✅ Бот запущен! Нажмите Ctrl+C для остановки.")
    
    # Запускаем бота в режиме polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()