# config.py
ADMIN_ID = 7966971037  # Ваш Telegram ID

BOT_STAGES = {
    'start': 'Начало',
    'category_selection': 'Выбор категории',
    'data_collection': 'Сбор данных',
    'filtering': 'Фильтрация',
    'tour_list': 'Список экскурсий',
    'tour_details': 'Детали экскурсии',
    'faq': 'FAQ',
    'booking': 'Бронирование'
}

QUESTION_TYPES = {
    'price': 'Цена',
    'children': 'Дети',
    'pregnancy': 'Беременность',
    'schedule': 'Расписание',
    'food': 'Питание',
    'transfer': 'Трансфер',
    'payment': 'Оплата',
    'other': 'Другое'
}

ERROR_TYPES = {
    'filter_error': 'Ошибка фильтрации',
    'tour_not_found': 'Экскурсия не найдена',
    'price_error': 'Ошибка цены',
    'db_error': 'Ошибка базы данных',
    'user_input': 'Некорректный ввод',
    'api_error': 'Ошибка API',
    'other': 'Другая ошибка'
}