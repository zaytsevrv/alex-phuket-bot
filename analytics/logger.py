# analytics/logger.py
import sqlite3
from datetime import datetime
import json

class AnalyticsLogger:
    def __init__(self, db_path='bot_statistics.db'):
        self.db_path = db_path
    
    def _execute_query(self, query, params=()):
        """Выполняет SQL запрос с обработкой ошибок"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Ошибка записи в БД: {e}")
            return False
    
    def log_action(self, user_id, action, stage=None, tour_id=None, category=None, session_data=None):
        """Логирует действие пользователя"""
        query = '''
        INSERT INTO user_actions (user_id, action, stage, tour_id, category, session_data, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        '''
        session_json = json.dumps(session_data) if session_data else None
        return self._execute_query(query, (user_id, action, stage, tour_id, category, session_json, datetime.now()))
    
    def log_tour_view(self, user_id, tour_id, tour_name, view_time_seconds, price_shown=None, category=None):
        """Логирует просмотр экскурсии"""
        query = '''
        INSERT INTO tour_views (user_id, tour_id, tour_name, view_time_seconds, price_shown, category, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        '''
        return self._execute_query(query, (user_id, tour_id, tour_name, view_time_seconds, price_shown, category, datetime.now()))
    
    def log_question(self, user_id, question_text, tour_name=None, bot_response=None, question_type=None):
        """Логирует вопрос пользователя"""
        query = '''
        INSERT INTO user_questions (user_id, question_text, tour_name, bot_response, question_type, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        '''
        return self._execute_query(query, (user_id, question_text, tour_name, bot_response, question_type, datetime.now()))
    
    def log_drop_off(self, user_id, drop_off_stage, last_action=None, session_duration=None, user_profile=None):
        """Логирует точку ухода пользователя"""
        profile_json = json.dumps(user_profile) if user_profile else None
        query = '''
        INSERT INTO drop_off_points (user_id, drop_off_stage, last_action, session_duration, user_profile, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        '''
        return self._execute_query(query, (user_id, drop_off_stage, last_action, session_duration, profile_json, datetime.now()))
    
    def log_error(self, error_type, error_message, user_id=None, bot_state=None, user_action=None):
        """Логирует ошибку бота"""
        query = '''
        INSERT INTO error_logs (error_type, error_message, user_id, bot_state, user_action, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        '''
        return self._execute_query(query, (error_type, error_message, user_id, bot_state, user_action, datetime.now()))
    
    def start_tour_view_session(self, user_id, tour_id):
        """Начинает отсчет времени просмотра экскурсии"""
        return {
            'user_id': user_id,
            'tour_id': tour_id,
            'start_time': datetime.now()
        }
    
    def end_tour_view_session(self, session_data, tour_name, price_shown=None, category=None):
        """Завершает отсчет времени просмотра и сохраняет в БД"""
        if not session_data:
            return False
        
        view_time = (datetime.now() - session_data['start_time']).seconds
        return self.log_tour_view(
            session_data['user_id'],
            session_data['tour_id'],
            tour_name,
            view_time,
            price_shown,
            category
        )

# Глобальный экземпляр логгера для импорта в других файлах
logger = AnalyticsLogger()