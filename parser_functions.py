#!/usr/bin/env python3
"""
Отдельный файл с функциями парсера для тестирования
"""
import re

def age_to_months(age_str):
    """Конвертирует возраст в месяцы"""
    if not age_str:
        return 0

    age_str = age_str.lower().strip()

    # Если уже в месяцах
    if 'мес' in age_str:
        try:
            num = int(re.search(r'(\d+)', age_str).group(1))
            return num
        except:
            return 0

    # Если в годах
    if 'лет' in age_str or 'год' in age_str:
        try:
            num = int(re.search(r'(\d+)', age_str).group(1))
            return num * 12
        except:
            return 0

    return 0

def format_age_months(months):
    """Форматирует возраст в месяцах в читаемый вид"""
    if months < 12:
        return f"{months} мес."
    else:
        years = months // 12
        rem_months = months % 12
        if rem_months == 0:
            return f"{years} лет"
        else:
            return f"{years} лет {rem_months} мес."

def _russian_year_label(n: int) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return "год"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return "года"
    return "лет"

def _russian_month_label(n: int) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return "месяц"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return "месяца"
    return "месяцев"

def parse_user_response(text):
    """
    Улучшенный анализатор ответов. Извлекает смысл из свободного текста.
    """
    text_lower = text.lower() if text else ""

    data = {
        'adults': 0,
        'children': [],        # возрасты в месяцах
        'children_original': [], # оригинальный текст возраста
        'pregnant': None,      # None = не указано
        'priorities': [],
        'health_issues': [],
        'raw_text': text
    }

    missing_points = []

    # ========== 1. СЛОВАРЬ ДЛЯ ПОИСКА ЧИСЛИТЕЛЬНЫХ ==========
    number_words = {
        'один': 1, 'одного': 1, 'одной': 1,
        'два': 2, 'двое': 2, 'двух': 2, 'вдвоем': 2,
        'три': 3, 'трое': 3, 'трёх': 3, 'трех': 3, 'втроем': 3,
        'четыре': 4, 'четверо': 4, 'четырех': 4, 'четырёх': 4, 'вчетвером': 4,
        'пять': 5, 'пятеро': 5,
        'шесть': 6, 'шестеро': 6,
        'семь': 7, 'семеро': 7,
        'восемь': 8, 'восьмеро': 8,
        'девять': 9, 'девятеро': 9,
        'десять': 10
    }

    # ========== СПЕЦИАЛЬНАЯ ОБРАБОТКА ВЗРОСЛЫХ ==========
    # Обрабатываем случаи типа "я одна", "я с мужем", "мы вдвоем"
    
    # Ищем паттерн "я одна/один"
    if 'я одна' in text_lower or 'я один' in text_lower:
        data['adults'] = 1
    
    # Ищем паттерн "я с [кем-то]"
    ya_s_match = re.search(r'я\s+с\s+(\w+)', text_lower)
    if ya_s_match:
        partner = ya_s_match.group(1)
        if partner in ['муж', 'мужем', 'жен', 'женой', 'партнёр', 'партнер', 'друг', 'подруг']:
            data['adults'] = 2
    
    # Ищем "мы вдвоем", "мы втроем" и т.д.
    my_v_match = re.search(r'мы\s+(в\d+ем)', text_lower)
    if my_v_match:
        v_word = my_v_match.group(1)
        if v_word == 'вдвоем':
            data['adults'] = 2
        elif v_word == 'втроем':
            data['adults'] = 3
        elif v_word == 'вчетвером':
            data['adults'] = 4
    all_numbers = []

    # 2A. Ищем цифры (учтём пунктуацию) - используем lookahead
    digit_pattern = r'(\d+)(?=\D|$)'
    for m in re.finditer(digit_pattern, text_lower):
        all_numbers.append({'value': int(m.group(1)), 'pos': m.start(), 'len': len(m.group(1)), 'type': 'digit'})

    # 2B. Ищем числительные-словом как отдельные токены
    for word, num in number_words.items():
        for m in re.finditer(r'\b' + re.escape(word) + r'\b', text_lower):
            all_numbers.append({'value': num, 'pos': m.start(), 'len': len(word), 'type': 'word', 'word': word})

    # Сортируем по позиции
    all_numbers.sort(key=lambda x: x['pos'])

    # Токенизируем текст (слова и числа с учётом пунктуации)
    tokens = []
    for m in re.finditer(r'\b\w+\b', text_lower):
        tokens.append({'text': m.group(0), 'start': m.start(), 'end': m.end()})

    def _find_token_index_for_pos(p):
        for i, t in enumerate(tokens):
            if t['start'] <= p < t['end']:
                return i
        # если не найдено, найдём ближайший
        best = None
        best_dist = None
        for i, t in enumerate(tokens):
            dist = min(abs(t['start'] - p), abs(t['end'] - p))
            if best is None or dist < best_dist:
                best = i
                best_dist = dist
        return best

    processed_positions = set()  # позиции уже обработанных чисел
    current_child_count = 1  # текущий счетчик количества детей для следующих возрастов

    for num_info in all_numbers:
        if num_info['pos'] in processed_positions:
            continue  # уже обработано в комбинированном паттерне
            
        num = num_info['value']
        pos = num_info['pos']
        t_idx = _find_token_index_for_pos(pos)

        left_context = tokens[t_idx-1]['text'] if t_idx is not None and t_idx-1 >= 0 else ''
        right_context = tokens[t_idx+1]['text'] if t_idx is not None and t_idx+1 < len(tokens) else ''

        # Если контекст явно говорит про взрослых
        if any(k in left_context or k in right_context for k in ['взросл', 'взр']):
            if data['adults'] == 0:
                data['adults'] = num
            processed_positions.add(pos)
            continue
        
        # Проверяем паттерны "нас/мы + число" для взрослых
        if left_context in ['нас', 'мы'] and right_context not in ['ребен', 'дет', 'детей', 'ребён', 'ребенка']:
            if data['adults'] == 0:
                data['adults'] = num
            processed_positions.add(pos)
            continue
        
        # Проверяем паттерны типа "я с мужем" (2 взрослых), "я одна" (1 взрослый)
        if left_context == 'я':
            if right_context in ['одна', 'один']:
                data['adults'] = 1
                processed_positions.add(pos)
                continue
            elif right_context in ['с', 'и']:
                # Смотрим дальше: "я с мужем" = 2, "я и муж" = 2
                next_right = tokens[t_idx+2]['text'] if t_idx is not None and t_idx+2 < len(tokens) else ''
                if next_right in ['муж', 'мужем', 'жен', 'женой', 'партнёр', 'партнер', 'друг', 'подруг']:
                    data['adults'] = 2
                    processed_positions.add(pos)
                    continue
        
        # Проверяем "вдвоем", "втроем" и т.д.
        if num_info['type'] == 'word' and num_info['word'] in ['вдвоем', 'втроем', 'вчетвером']:
            # Ищем контекст
            context_window = ' '.join(t['text'] for t in tokens[max(0, t_idx-3):min(len(tokens), t_idx+4)])
            if 'ребен' not in context_window and 'дет' not in context_window:
                data['adults'] = num
                processed_positions.add(pos)
                continue
        
        # Если число явно указывает количество детей (перед "дети", "ребенок")
        if right_context in ['ребен', 'дет', 'детей', 'ребён', 'ребенка']:
            current_child_count = num
            processed_positions.add(pos)
            continue  # не обрабатывать как возраст

        # Если рядом слова ребенок/дети или рядом слова года/лет/месяц - это возраст
        if any(k in left_context or k in right_context for k in ['ребен', 'дет', 'детей', 'ребён', 'ребенка']) or \
           any(k in right_context for k in ['лет', 'год', 'г', 'мес', 'месяц']):

            # Берём окно токенов вокруг
            start = max(0, t_idx - 5)
            end = min(len(tokens), t_idx + 6)
            context_phrase = ' '.join(t['text'] for t in tokens[start:end])

            # Ищем комбинированный паттерн "X год(а/лет) ... Y месяц(ев)"
            age_match = re.search(r'(\d+)\s*(?:лет|год(?:а|ов)?|г\.?)+\s*(?:и\s*)?(\d+)?\s*(?:месяц(?:а|ев)?|мес\.?)+', context_phrase)
            if age_match:
                years = int(age_match.group(1))
                months = int(age_match.group(2)) if age_match.group(2) else 0
                total_months = years * 12 + months
                
                # Добавляем детей с этим возрастом (используем current_child_count)
                for _ in range(current_child_count):
                    data['children'].append(total_months)
                    # Формируем человекочитаемый текст
                    if months == 0:
                        data['children_original'].append(f"{years} {_russian_year_label(years)}")
                    else:
                        data['children_original'].append(f"{years} {_russian_year_label(years)} и {months} {_russian_month_label(months)}")
                current_child_count = 1  # сбрасываем после использования
                
                # Помечаем все числа в диапазоне контекста как обработанные
                context_start_pos = tokens[start]['start']
                context_end_pos = tokens[end-1]['end']
                for num_info_check in all_numbers:
                    if context_start_pos <= num_info_check['pos'] < context_end_pos:
                        processed_positions.add(num_info_check['pos'])
                continue

            # Если указано в годах
            if any(k in right_context for k in ['лет', 'год', 'г.']):
                months = age_to_months(f"{num} лет")
                if months > 0:
                    for _ in range(current_child_count):
                        data['children'].append(months)
                        data['children_original'].append(f"{num} {_russian_year_label(num)}")
                    current_child_count = 1
                processed_positions.add(pos)
                continue

            # Если указано в месяцах
            if any(k in right_context for k in ['месяц', 'мес']):
                months = int(num)
                if 0 < months < 216:
                    for _ in range(current_child_count):
                        data['children'].append(months)
                        data['children_original'].append(f"{months} {_russian_month_label(months)}")
                    current_child_count = 1
                processed_positions.add(pos)
                continue

            # Если рядом слово 'ребен'/'дет' и нет единиц измерения — это количество детей (маркер)
            if any(k in context_phrase for k in ['ребен', 'дет', 'детей']):
                # добавляем маркер 0 (возраст не указан)
                data['children'].append(0)
                data['children_original'].append('количество')
                processed_positions.add(pos)
                continue

    # ========== 5. ПОИСК БЕРЕМЕННОСТИ, ПРИОРИТЕТОВ И ЗДОРОВЬЯ ==========
    # (Эти блоки остаются почти как были, они работают хорошо)
    pregnant_keywords = ['беременн', 'в положении', 'жду ребёнка', 'жду ребенка']
    not_pregnant_keywords = ['не беременн', 'нет беременн', 'не в положении']

    pregnant_mentioned = False
    for keyword in not_pregnant_keywords:
        if keyword in text_lower:
            data['pregnant'] = False
            pregnant_mentioned = True
            break

    if not pregnant_mentioned:
        for keyword in pregnant_keywords:
            if keyword in text_lower:
                data['pregnant'] = True
                pregnant_mentioned = True
                break

    # Приоритеты
    priority_keywords = {
        'комфорт': ['комфорт', 'удобств', 'плавн', 'мягк'],
        'бюджет': ['бюджет', 'дешев', 'эконом', 'недорог'],
        'фотографии': ['фото', 'сним', 'инстаграм', 'красив'],
        'не рано вставать': ['не рано', 'поспать', 'поздн', 'не люблю рано', 'не хочу рано'],
    }

    for priority, keywords in priority_keywords.items():
        for keyword in keywords:
            if keyword in text_lower:
                if priority not in data['priorities']:
                    data['priorities'].append(priority)
                break

    # Проблемы со здоровьем
    health_keywords = {
        'спина': ['спин', 'поясниц'],
        'укачивание': ['укачиван', 'морск', 'тошн'],
        'ходьба': ['ходьб', 'ходить трудн', 'ноги болят'],
    }

    for issue, keywords in health_keywords.items():
        for keyword in keywords:
            if keyword in data['raw_text'].lower():
                if issue not in data['health_issues']:
                    data['health_issues'].append(issue)
                break

    # ========== 6. ПРОВЕРКА, ЧТО ПРОПУЩЕНО ==========
    if data['adults'] == 0:
        missing_points.append("количество взрослых")

    if data['pregnant'] is None:
        missing_points.append("беременность (да/нет)")

    # Проверяем информацию о детях
    words = text_lower.split()
    if any('ребен' in word or 'дет' in word for word in words):
        # Если упомянули детей, но возрастов нет и не написали "без детей"
        if not data['children'] and 'без детей' not in text_lower and 'нет детей' not in text_lower:
            missing_points.append("информация о детях")
    elif data['adults'] > 0:
        # Если взрослые есть, но о детях ничего не сказано — спрашиваем
        missing_points.append("информация о детях")

# ========== 7. Убираем только маркеры количества, сохраняем дубликаты реальных возрастов ==========
    # Если есть и конкретные возрасты, и маркер "количество" (0) - удаляем маркер
    if 0 in data['children'] and len([age for age in data['children'] if age > 0]) > 0:
        data['children'] = [age for age in data['children'] if age != 0]
        data['children_original'] = [orig for orig in data['children_original'] if orig != 'количество']

    return data, missing_points