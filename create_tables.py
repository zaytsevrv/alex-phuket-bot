# create_tables.py
import sqlite3
from datetime import datetime

def init_analytics_database():
    """Создает расширенную базу данных для аналитики"""
    conn = sqlite3.connect('bot_statistics.db')
    cursor = conn.cursor()
    
    # 1. Таблица действий пользователей (расширенная)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        stage TEXT,
        tour_id INTEGER,
        category TEXT,
        session_data TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 2. Таблица просмотров экскурсий (с временем)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tour_views (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        tour_id INTEGER NOT NULL,
        tour_name TEXT,
        view_time_seconds INTEGER,
        price_shown TEXT,
        category TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 3. Таблица вопросов пользователей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        question_text TEXT NOT NULL,
        tour_name TEXT,
        bot_response TEXT,
        question_type TEXT,
        was_helpful BOOLEAN,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 4. Таблица точек ухода (drop-off points)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS drop_off_points (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        drop_off_stage TEXT NOT NULL,
        last_action TEXT,
        session_duration INTEGER,
        user_profile TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 5. Таблица ошибок
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS error_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        error_type TEXT NOT NULL,
        error_message TEXT,
        user_id INTEGER,
        bot_state TEXT,
        user_action TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Создаем индексы для быстрого поиска
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_actions_user ON user_actions(user_id, timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_actions_type ON user_actions(action, timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_drops_stage ON drop_off_points(drop_off_stage, timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_errors_type ON error_logs(error_type, timestamp)')
    
    conn.commit()
    conn.close()
    print("✅ Расширенная база данных для аналитики создана!")
    print("   Таблицы: user_actions, tour_views, user_questions, drop_off_points, error_logs")

if __name__ == "__main__":
    init_analytics_database()