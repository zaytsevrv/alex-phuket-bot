import csv
import logging
import re
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
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

# === АНАЛИТИКА ===
from analytics.logger import logger
from config import ADMIN_ID, BOT_STAGES, QUESTION_TYPES, ERROR_TYPES
import json
# === КОНЕЦ ИМПОРТОВ АНАЛИТИКИ ===

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

# === КОНЕЦ БЛОКА БЕЗОПАСНОЙ ЗАГРУЗКИ ТОКЕНА ===
# ==================== БАЗА ДАННЫХ ====================
DB_FILE = "bot_statistics.db"

# ==================== НАСТРОЙКИ ====================
# Замените на ваш токен!
CSV_FILE = "Price22.12.2025.csv"

# Состояния диалога (шаги)
CATEGORY, QUALIFICATION, TOUR_DETAILS, QUESTION = range(4)

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

# Клавиатура с категориями
def make_category_keyboard():
    categories = get_categories()
    # Создаем кнопки по 2 в ряд
    keyboard = []
    for i in range(0, len(categories), 2):
        row = categories[i:i+2]
        keyboard.append(row)
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

# ==================== ФУНКЦИЯ ДЛЯ КОНВЕРТАЦИИ ВОЗРАСТА ====================
def age_to_months(age_str):
    """
    Конвертирует текст возраста в месяцы для точной проверки ограничений.
    Примеры:
    - "5 лет" → 60 месяцев
    - "1 год 3 месяца" → 15 месяцев
    - "10 месяцев" → 10 месяцев
    - "2 года" → 24 месяца
    """
    if not age_str:
        return 0
    
    age_str = str(age_str).lower().strip()
    total_months = 0
    
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
    
    # Если просто число без указания единиц (например "5"), считаем что это годы
    if total_months == 0 and age_str.isdigit():
        total_months = int(age_str) * 12
    
    return total_months

def format_age_months(months):
    """
    Форматирует возраст в месяцах в читаемый вид.
    Примеры:
    - 10 → "10 мес."
    - 15 → "1 год 3 мес." (15 месяцев = 1 год 3 месяца)
    - 24 → "2 года" (24 месяца = 2 года)
    - 37 → "3 года 1 мес." (37 месяцев = 3 года 1 месяц)
    """
    if months < 12:
        return f"{months} мес."
    elif months == 12:
        return "1 год"
    elif months < 24:
        remaining = months - 12
        return f"1 год {remaining} мес."
    else:
        years = months // 12  # Целочисленное деление - округление в меньшую сторону
        remaining_months = months % 12
        
        if years == 1:
            year_word = "год"
        elif 2 <= years <= 4:
            year_word = "года"
        else:
            year_word = "лет"
        
        if remaining_months == 0:
            return f"{years} {year_word}"
        else:
            return f"{years} {year_word} {remaining_months} мес."

# ==================== ФИЛЬТРАЦИЯ ЭКСКУРСИЙ ПО БЕЗОПАСНОСТИ ====================
def filter_tours_by_safety(tours, user_data):
    """
    Фильтрует экскурсии по критериям безопасности:
    1. Беременность - исключает опасные экскурсии
    2. Возраст детей - проверяет ограничения по возрасту
    3. Проблемы со здоровьем
    """
    filtered_tours = []
    
    is_pregnant = user_data.get('pregnant', False)
    children_ages = user_data.get('children', [])  # возрасты в месяцах
    health_issues = user_data.get('health_issues', [])
    
    for tour in tours:
        # Проверяем, можно ли показывать эту экскурсию
        is_safe = True
        
        # 1. Проверка на беременность
        if is_pregnant:
            tour_name = tour.get("Название", "").lower()
            tour_description = tour.get("Описание", "").lower()
            
            # Список опасных активностей для беременных
            dangerous_keywords = ['аквапарк', 'дайвинг', 'серфинг', 'рафтинг', 'байк', 
                                 'квадроцикл', 'сёрфинг', 'экстрим', 'экстремальн', 
                                 'анимал шоу', 'глубокое море', 'шхуна', 'активные туры']
            
            for keyword in dangerous_keywords:
                if keyword in tour_name or keyword in tour_description:
                    is_safe = False
                    break
        
        # 2. Проверка возраста детей
        if children_ages:
            tour_category = tour.get("Для информации", "").lower()
            tour_name = tour.get("Название", "").lower()
            
            # Для морских туров дети до 1 года - не рекомендуются
            if any(age < 12 for age in children_ages):
                if any(keyword in tour_category for keyword in ['море', 'остров', 'морск']):
                    # Проверяем, есть ли явное предупреждение в названии
                    if not any(keyword in tour_name for keyword in ['семейн', 'детск', 'мягк', 'комфорт']):
                        is_safe = False
            
            # Проверяем минимальный возраст для определенных экскурсий
            tour_min_age = tour.get("Мин. возраст", "")
            if tour_min_age and tour_min_age.isdigit():
                min_age_months = int(tour_min_age) * 12
                if any(age < min_age_months for age in children_ages):
                    is_safe = False
        
        # 3. Проверка проблем со здоровьем
        if health_issues:
            tour_description = tour.get("Описание", "").lower()
            
            # Если проблемы со спиной - исключаем длительные пешие туры
            if 'спина' in health_issues and 'пешеход' in tour_description:
                if 'легк' not in tour_description and 'коротк' not in tour_description:
                    is_safe = False
            
            # Если проблемы с укачиванием - исключаем морские туры
            if 'укачивание' in health_issues:
                if any(keyword in tour_description for keyword in ['море', 'катер', 'яхт', 'паром', 'корабль']):
                    is_safe = False
            
            # Если проблемы с ходьбой - исключаем пешие экскурсии
            if 'ходьба' in health_issues:
                if any(keyword in tour_description for keyword in ['пеший', 'пешком', 'ходьб', 'прогулк']):
                    is_safe = False
        
        # Если экскурсия безопасна - добавляем в результат
        if is_safe:
            filtered_tours.append(tour)
    
    return filtered_tours

# ==================== РАНЖИРОВАНИЕ ЭКСКУРСИЙ ПО ПРИОРИТЕТАМ ====================
def rank_tours_by_priorities(tours, user_data):
    """
    Ранжирует экскурсии по приоритетам пользователя
    """
    priorities = user_data.get('priorities', [])
    
    if not priorities:
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
    
    if days and days.strip() and days.strip().lower() != "ежедневно":
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
    
    if keywords and keywords.strip():
        # Форматируем ключевые слова
        keywords_clean = keywords.strip()
        if len(keywords_clean) > 100:
            keywords_clean = keywords_clean[:100] + "..."
        info_text += f"**🔍 Ключевые слова:** {keywords_clean}\n"
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
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"prev_{offset-limit}"))
    
    if offset + limit < len(tours):
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"next_{offset+limit}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # ⭐ ДОБАВИЛИ КНОПКУ "ЗАДАТЬ ВОПРОС"
    if show_question_button:
        keyboard.append([InlineKeyboardButton("🤔 Задать вопрос", callback_data="ask_question")])
    
    keyboard.append([InlineKeyboardButton("🔄 Выбрать другую категорию", callback_data="change_category")])
    
    return InlineKeyboardMarkup(keyboard)

# ==================== АНАЛИЗ ОТВЕТОВ ПОЛЬЗОВАТЕЛЯ ====================
def parse_user_response(text):
    """
    Анализирует ответ пользователя и извлекает структурированные данные.
    Возвращает словарь с найденной информацией и список пропущенных пунктов.
    """
    text_lower = text.lower()
    
    # Инициализируем структуру данных
    data = {
        'adults': 0,
        'children': [],  # список возрастов детей В МЕСЯЦАХ
        'children_original': [],  # оригинальные тексты возрастов для отображения
        'pregnant': None,  # None = не указано, True/False = указано
        'priorities': [],
        'health_issues': [],
        'raw_text': text
    }
    
    missing_points = []
    
    # 1. Поиск количества взрослых (самый простой паттерн)
    adult_patterns = [
        r'(\d+)\s*взросл',  # "2 взрослых"
        r'взросл[а-я]+\s*(\d+)',  # "взрослых 2"
        r'(\d+)\s*взр',  # "2 взр"
    ]
    
    adults_found = False
    for pattern in adult_patterns:
        match = re.search(pattern, text_lower)
        if match:
            data['adults'] = int(match.group(1))
            adults_found = True
            break
    
    if not adults_found:
        # Попробуем найти просто цифры в начале
        match = re.search(r'^(\d+)\s', text_lower)
        if match:
            data['adults'] = int(match.group(1))
            adults_found = True
    
    # 2. Поиск детей и их возрастов
    # Обновленные паттерны для поддержки месяцев
    child_patterns = [
        r'(\d+)\s*ребен[а-я]+\s*(\d+)\s*(?:лет|год[а]?)\s*и\s*(\d+)\s*(?:лет|год[а]?)',  # "2 ребенка 5 лет и 7 лет"
        r'(\d+)\s*ребен[а-я]+\s*(\d+)\s*и\s*(\d+)\s*(?:лет|год[а]?)',  # "2 ребенка 5 и 7 лет"
        r'ребен[а-я]+\s*(\d+)\s*(?:лет|год[а]?)',  # "ребенок 5 лет"
        r'дет[а-я]+\s*(\d+)\s*(?:лет|год[а]?)',  # "дети 5 лет"
        r'(\d+)\s*годн?[а-я]*\s*ребен',  # "5-летний ребенка"
        r'(\d+)\s*годн?[а-я]*\s*дет',  # "5-летний дет"
        # Паттерны для месяцев
        r'ребен[а-я]+\s*(\d+)\s*(?:месяц[а-я]*|мес\.?)',  # "ребенок 10 месяцев"
        r'дет[а-я]+\s*(\d+)\s*(?:месяц[а-я]*|мес\.?)',  # "дети 10 месяцев"
        r'ребен[а-я]+\s*(\d+)\s*(?:лет|год[а]?)\s*(\d+)\s*(?:месяц[а-я]*|мес\.?)',  # "ребенок 1 год 3 месяца"
        r'дет[а-я]+\s*(\d+)\s*(?:лет|год[а]?)\s*(\d+)\s*(?:месяц[а-я]*|мес\.?)',  # "дети 1 год 3 месяца"
    ]
    
    children_found = False
    for pattern in child_patterns:
        matches = re.findall(pattern, text_lower)
        for match in matches:
            if isinstance(match, tuple):
                # Пропускаем первый элемент (количество детей), берём только возрасты
                for age in match[1:]:
                    if age and str(age).isdigit():
                        months = age_to_months(age)
                        if months > 0:
                            data['children'].append(months)
                            data['children_original'].append(str(age))
                            children_found = True
            elif isinstance(match, str) and match.isdigit():
                months = age_to_months(match)
                if months > 0:
                    data['children'].append(months)
                    data['children_original'].append(match)
                    children_found = True
    
    # 3. Поиск беременности
    pregnant_keywords = ['беременн', 'в положении', 'ожидаем']
    not_pregnant_keywords = ['не беременн', 'нет беременн', 'не в положении']
    
    pregnant_mentioned = False
    
    # СНАЧАЛА проверяем ОТРИЦАНИЯ (это важно!)
    for keyword in not_pregnant_keywords:
        if keyword in text_lower:
            data['pregnant'] = False
            pregnant_mentioned = True
            break
    
    # ЕСЛИ отрицаний не нашли, проверяем утверждения
    if not pregnant_mentioned:
        for keyword in pregnant_keywords:
            if keyword in text_lower:
                data['pregnant'] = True
                pregnant_mentioned = True
                break
    
    # 4. Поиск приоритеты
    priority_keywords = {
        'комфорт': ['комфорт', 'удобств', 'плавн', 'мягк'],
        'бюджет': ['бюджет', 'дешев', 'эконом', 'недорог'],
        'фотографии': ['фото', 'сним', 'инстаграм', 'красив'],
        'не рано вставать': ['не рано', 'поспать', 'поздн', 'не люблю рано', 'не хочу рано'],
        'без толп': ['без толп', 'мало людей', 'пуст', 'уединен'],
    }
    
    for priority, keywords in priority_keywords.items():
        for keyword in keywords:
            if keyword in text_lower:
                if priority not in data['priorities']:
                    data['priorities'].append(priority)
                break
    
    # 5. Поиск проблем со здоровьем
    health_keywords = {
        'спина': ['спин', 'поясниц', 'позвоночн'],
        'укачивание': ['укачиван', 'морск', 'тошн', 'качк'],
        'ходьба': ['ходить', 'ног', 'ходьб', 'пешком трудн'],
    }
    
    for issue, keywords in health_keywords.items():
        for keyword in keywords:
            if keyword in text_lower:
                if issue not in data['health_issues']:
                    data['health_issues'].append(issue)
                break
    
    # 6. Определяем, что пропущено (для уточняющих вопросов)
    if data['adults'] == 0:
        missing_points.append("количество взрослых")
    
    if data['pregnant'] is None:
        missing_points.append("беременность (да/нет)")
    
    # Если есть взрослые, но нет информации о детях - тоже пропущено
    # ИЛИ если взрослые не указаны, но и про детей ничего не сказано - тоже спрашиваем
    if (data['adults'] > 0 and not children_found) or (data['adults'] == 0):
        # Проверим, может пользователь написал "без детей" или "нет детей"
        if 'без детей' not in text_lower and 'нет детей' not in text_lower:
            missing_points.append("информация о детях")
    
    return data, missing_points

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

# === АНАЛИТИКА: ТРЕКИНГ СЕССИИ ===
    track_user_session(context, BOT_STAGES['start'])
    logger.log_action(user.id, "started_bot", stage=BOT_STAGES['start'])
    context.user_data['last_action'] = 'start'
    # === КОНЕЦ АНАЛИТИКИ ===

    welcome_text = f"""Приветствую, {user.first_name}! 🙏

Я Алекс, ваш личный гид по сокровищам Пхукета от GoldenKeyTours.

Я помогу превратить ваши "хочу" в незабываемые впечатления. Подскажите, о чём мечтаете?"""
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=make_category_keyboard()
    )
    return CATEGORY

async def handle_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пользователь выбрал категорию"""
    user_choice = update.message.text
    context.user_data['category'] = user_choice

# === АНАЛИТИКА: ВЫБОР КАТЕГОРИИ ===
    user = update.effective_user
    track_user_session(context, BOT_STAGES['category_selection'], {'category': user_choice})
    logger.log_action(user.id, "chose_category", stage=BOT_STAGES['category_selection'], category=user_choice)
    context.user_data['last_action'] = 'category_choice'
    # === КОНЕЦ АНАЛИТИКИ ===
    
    # Сохраняем экскурсии этой категории
    category_tours = [t for t in TOURS if t.get("Для информации", "") == user_choice]
    context.user_data['filtered_tours'] = category_tours
    
    # Считаем хиты в категории
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
    response += "1️⃣ *Состав группы:* Сколько взрослых и детей? Укажите возраст каждого ребенка (например: 5 лет, 1 год 3 месяца, 10 месяцев).\n"
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
    return QUALIFICATION

async def handle_qualification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пользователь ответил на вопросы - анализируем и уточняем при необходимости"""
    user_text = update.message.text
    context.user_data['qualification_raw'] = user_text

# === АНАЛИТИКА: ОБРАБОТКА ДАННЫХ ПОЛЬЗОВАТЕЛЯ ===
    user = update.effective_user
    track_user_session(context, BOT_STAGES['data_collection'])
    logger.log_action(user.id, "provided_user_data", stage=BOT_STAGES['data_collection'])
    context.user_data['last_action'] = 'user_data_input'
    # === КОНЕЦ АНАЛИТИКИ ===
    
    # Анализируем ответ
    user_data, missing_points = parse_user_response(user_text)
    context.user_data['user_data'] = user_data
    
    # Проверяем, все ли обязательные пункты заполнены
    mandatory_points = ["количество взрослых", "беременность (да/нет)", "информация о детях"]

    # Список действительно пропущенных обязательных пунктов
    really_missing = [point for point in mandatory_points if point in missing_points]
    
    if really_missing:
        # Формируем уточняющий вопрос
        response = "🤔 Спасибо за информацию! Чтобы подобрать безопасные варианты, мне нужно уточнить:\n\n"
        
        for i, point in enumerate(really_missing, 1):
            if point == "количество взрослых":
                response += f"{i}️⃣ *Сколько взрослых* в вашей группе?\n"
            elif point == "беременность (да/нет)":
                response += f"{i}️⃣ *Есть ли беременные* в группе? (Это важно для безопасности!)\n"
            elif point == "информация о детях":
                response += f"{i}️⃣ *Есть ли дети*? Если да, укажите возраст каждого ребенка (например: 5 лет, 1 год 3 месяца).\n"
        
        response += "\nПожалуйста, ответьте на эти вопросы, например:\n"
        response += "_«2 взрослых, не беременны, детей нет»_"
        
        await update.message.reply_text(
            response,
            parse_mode='Markdown'
        )
        return QUALIFICATION  # Остаёмся в этом же состоянии для уточнений
    
    # ВСЁ заполнено - можно показывать экскурсии!
    category = context.user_data.get('category', 'неизвестно')
    category_tours = context.user_data.get('filtered_tours', [])
    
    # Формируем сводку
    response = f"✅ *Отлично! Всё понял.*\n\n"
    response += f"*Категория:* {category}\n"
    response += f"*Состав группы:* {user_data['adults']} взрослых"
    
    if user_data['children']:
        # Форматируем возрасты для отображения (с округлением в меньшую сторону)
        age_texts = []
        for months in user_data['children']:
            age_texts.append(format_age_months(months))
        
        ages_display = ', '.join(age_texts)
        children_count = len(user_data['children'])
        # Правильное склонение
        if children_count == 1:
            children_text = "1 ребенок"
        elif children_count in [2, 3, 4]:
            children_text = f"{children_count} ребенка"
        else:
            children_text = f"{children_count} детей"
        response += f", {children_text} ({ages_display})"
        
        # Проверяем есть ли дети до 1 года (опасно для морских туров)
        infants = [age for age in user_data['children'] if age < 12]
        if infants and any(cat in category.lower() for cat in ['море', 'остров', 'морск']):
            response += "\n\n⚠️ *Внимание:* Детям до 1 года морские экскурсии не рекомендуются для безопасности."
    else:
        response += ", детей нет"
    
    if user_data['pregnant'] is None:
        pregnancy_text = 'Не указано'
    else:
        pregnancy_text = 'Есть' if user_data['pregnant'] else 'Нет'
    response += f"\n*Беременность:* {pregnancy_text}"
    
    if user_data['priorities']:
        response += f"\n*Важные моменты:* {', '.join(user_data['priorities'])}"
    
    if user_data['health_issues']:
        response += f"\n*Учтём здоровье:* {', '.join(user_data['health_issues'])}"
    
    response += "\n\n🔍 *Ищем идеальные варианты для вас...*\n"
    
    # 1. Фильтруем по безопасности
    safe_tours = filter_tours_by_safety(category_tours, user_data)
    context.user_data['safe_tours'] = safe_tours
    
    # 2. Ранжируем по приоритетам
    ranked_tours = rank_tours_by_priorities(safe_tours, user_data)
    context.user_data['ranked_tours'] = ranked_tours
    
    # 3. Сохраняем текущий offset
    context.user_data['tour_offset'] = 0
    
    if not ranked_tours:
        response += "\n❌ *К сожалению, по вашим критериям не найдено подходящих экскурсий.*\n"
        response += "Попробуйте:\n"
        response += "• Изменить параметры поиска\n"
        response += "• Выбрать другую категорию\n"
        response += "• Написать /start чтобы начать заново"
        
        await update.message.reply_text(response, parse_mode='Markdown')
        return ConversationHandler.END
    
    response += f"\n✅ *Найдено {len(ranked_tours)} подходящих экскурсий!*\n"
    response += f"\n📋 *Топ-{min(5, len(ranked_tours))} рекомендованных вариантов:*"
    
    # Показываем клавиатуру с экскурсиями
    await update.message.reply_text(
        response,
        parse_mode='Markdown',
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
            
            # ИСПОЛЬЗУЕМ НОВОЕ ФОРМАТИРОВАНИЕ В СТИЛЕ АЛЕКСА
            description = format_tour_description_alex_style(tour)
            
            # Создаем кнопки для навигации
            keyboard = [
                [InlineKeyboardButton("📋 Дополнительная информация", callback_data=f"more_info_{tour_index}")],
                [InlineKeyboardButton("🤔 Задать вопрос", callback_data="ask_question")],
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
            reply_markup=make_tours_keyboard(ranked_tours, offset, 5)
        )
    
    elif callback_data == "back_to_list_0":
        # Возврат к списку экскурсий
        ranked_tours = context.user_data.get('ranked_tours', [])
        offset = context.user_data.get('tour_offset', 0)
        
        await query.edit_message_text(
            text=f"📋 *Доступные экскурсии ({len(ranked_tours)} вариантов):*",
            parse_mode='Markdown',
            reply_markup=make_tours_keyboard(ranked_tours, offset, 5)
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
        response += f"   Взрослый: {price_adult}฿, Детский: {price_child}฿\n\n"
    
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

# ==================== КОМАНДА СТАТИСТИКИ ====================
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
        response += f"• Выбор категории: {chose_category} ({chose_category/started_bot*100:.1f}% от стартов)\n"
        response += f"• Просмотр экскурсий: {viewed_tour} ({viewed_tour/started_bot*100:.1f}% от стартов)\n\n"
        
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
👨‍👩‍👧‍👦 **Дети и возрастные ограничения:**

Проверяйте **теги в описании** экскурсии:
• #дети_от_1_года — можно с 1 года
• #дети_от_2_лет — можно с 2 лет
• #дети_от_4_лет — можно с 4 лет
• #дети_от_7_лет — можно с 7 лет
• #от_18_лет — только взрослые

*Если заболел ребёнок — особые условия возврата в полных правилах:*
👉 [Правила бронирования](https://goldenkeytours.com/booking-and-cancellation-conditions)
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
        answer = """
🤒 **Если кто-то заболел:**

Полный возврат возможен **только при предоставлении справки из международного госпиталя до 16:00** накануне экскурсии.

📋 **Важные условия:**
• Справка только из международного ГОСПИТАЛЯ
• Предоставить до 16:00 дня перед экскурсией
• Возврат только для заболевшего
• Если заболел ребёнок — возврат на ребёнка + одного родителя
• Для двухдневных морских туров — штраф 50%
• Для Симилан — штраф 1000฿/500฿

👉 *Все детали в* [Правилах бронирования](https://goldenkeytours.com/booking-and-cancellation-conditions)
"""
        await update.message.reply_text(
            answer,
            parse_mode='Markdown',
            reply_markup=make_question_keyboard()
        )
        return QUESTION
    
    elif any(word in question_text for word in ['вернут', 'отмен', 'передума', 'не поеду', 'возврат деньг', 'верните', 'отказаться', 'передумываю']):
        answer = """
🔄 **Отмена и возврат средств:**

• **Более чем за 24 часа до тура** → возвращается **50%**
• **Менее чем за 24 часа** → возврата нет
• **В день тура** → возврата нет
• **Авиатуры/индивидуальные туры** → возврата нет
• **Дельфинарий** → возврата нет ни при каких условиях

⚠️ **Обратите внимание:** 
Если вы внесли предоплату, но остаётся доплата гиду в день тура — эту доплату нужно внести, даже если кто-то из группы откажется.

👉 *Все исключения и условия в* [Правилах бронирования](https://goldenkeytours.com/booking-and-cancellation-conditions)
"""
        await update.message.reply_text(
            answer,
            parse_mode='Markdown',
            reply_markup=make_question_keyboard()
        )
        return QUESTION
    
    elif any(word in question_text for word in ['шторм', 'погод', 'дожд', 'отменят', 'ливень', 'ураган', 'тайфун', 'непогода']):
        answer = """
🌧️ **Погодные условия:**

• Экскурсия отменяется только при **штормовом предупреждении** (возврат или перенос)
• Обычный дождь не причина для отмены — на Пхукете дождь часто локальный
• Если экскурсию отменяет организатор (погода, недобор) — предлагают: возврат, перенос или замену

👉 *Подробнее в* [Правилах бронирования](https://goldenkeytours.com/booking-and-cancellation-conditions)
"""
        await update.message.reply_text(
            answer,
            parse_mode='Markdown',
            reply_markup=make_question_keyboard()
        )
        return QUESTION
    
    elif any(word in question_text for word in ['доплат', 'трансфер дорог', 'дорого трансфер', 'оплата трансфер']):
        answer = """
🚗 **Доплата за трансфер:**

• Чаще всего трансфер бесплатный с пляжей Ката, Карон, Патонг
• Для удалённых районов возможна доплата 200-500฿
• Точную стоимость определяет менеджер после выбора отеля
• Информация о возможных доплатах есть в разделе "Важная информация" каждой экскурсии

👉 *Проверим конкретно по вашему отелю после выбора экскурсии*
"""
        await update.message.reply_text(
            answer,
            parse_mode='Markdown',
            reply_markup=make_question_keyboard()
        )
        return QUESTION
    
    # 4. Если вопрос не распознан
    else:
        answer = """
🤔 **Я понял ваш вопрос!**

У меня есть готовые ответы на самые частые темы — выберите одну из кнопок выше.

🎯 **Если вопрос срочный:**
1. Выберите ближайшую тему
2. После согласования экскурсии
3. Я передам заявку менеджеру
4. Он ответит на всё подробно!

*Обязательно ознакомьтесь с* 👉 [Правилами бронирования](https://goldenkeytours.com/booking-and-cancellation-conditions)
"""
        await update.message.reply_text(
            answer,
            parse_mode='Markdown',
            reply_markup=make_question_keyboard()
        )
        return QUESTION

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
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category)
            ],
            QUALIFICATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_qualification)
            ],
            TOUR_DETAILS: [
                CallbackQueryHandler(handle_tour_selection)
            ],
            QUESTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question)
            ],
         },
         fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Добавляем обработчики
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("tours", show_tours))
    application.add_handler(CommandHandler("debug", debug_info))
    application.add_handler(CommandHandler("stats", stats_command))
    
    print("✅ Бот запущен! Нажмите Ctrl+C для остановки.")
    
    # Запускаем бота в режиме polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()