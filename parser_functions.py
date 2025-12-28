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
    """Форматирует возраст в месяцах в читаемый вид в годах с округлением в меньшую сторону"""
    if months < 12:
        return "менее 1 года"
    else:
        years = months // 12  # округление в меньшую сторону
        return f"{years} {_russian_year_label(years)}"

def generate_confirmation_summary(data):
    """Генерирует сводку для подтверждения пользователем"""
    lines = []
    
    # Взрослые
    if data['adults'] > 0:
        lines.append(f"Взрослых: {data['adults']}")
    
    # Дети
    if data['children']:
        child_ages = []
        for months in data['children']:
            age_str = format_age_months(months)
            child_ages.append(age_str)
        children_text = f"Дети: {len(data['children'])} ({'; '.join(child_ages)})"
        lines.append(children_text)
    else:
        lines.append("Детей: нет")
    
    # Беременность
    if data['pregnant'] is True:
        lines.append("Беременность: да")
    elif data['pregnant'] is False:
        lines.append("Беременность: нет")
    else:
        lines.append("Беременность: не указано")
    
    return "\n".join(lines)

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
        total_people = 0
        if v_word == 'вдвоем':
            total_people = 2
        elif v_word == 'втроем':
            total_people = 3
        elif v_word == 'вчетвером':
            total_people = 4
        
        # Если есть дети, вычитаем их из общего числа
        if 'ребен' in text_lower or 'дет' in text_lower:
            child_count = len(data['children']) if data['children'] else 0
            data['adults'] = max(1, total_people - child_count)
        else:
            data['adults'] = total_people

    # ========== 2. СБОР ВСЕХ ЧИСЕЛ ==========
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

    # ========== 3. ПАРСИНГ ДЕТЕЙ ==========
    # Сначала ищем количества детей, затем возраста
    
    # Ищем паттерны типа "двое детей", "трое детей" и т.д.
    child_count_patterns = [
        (r'(\w+)\s+дет', lambda w: number_words.get(w, 0)),  # "двое детей"
        (r'(\w+)\s+ребен', lambda w: number_words.get(w, 0)), # "двое детей"
    ]
    
    child_counts = []
    for pattern, converter in child_count_patterns:
        for m in re.finditer(pattern, text_lower):
            word = m.group(1)
            count = converter(word)
            if count > 0:
                child_counts.append(count)
                # Помечаем позицию как обработанную
                processed_positions.add(m.start())
    
    # Если нашли количества детей, используем максимальное
    if child_counts:
        expected_children = max(child_counts)
    else:
        expected_children = 0
    
    # Теперь ищем возраста детей
    age_patterns = []
    
    # Ищем комбинированные возраста типа "7 лет и 10 месяцев" - разделяем на два возраста
    for m in re.finditer(r'(\d+)\s*(?:лет|год(?:а|ов)?|г\.?)+\s*(?:и\s*)?(\d+)?\s*(?:месяц(?:а|ев)?|мес\.?)+', text_lower):
        years = int(m.group(1))
        months = int(m.group(2)) if m.group(2) else 0
        # Добавляем два отдельных возраста
        age_patterns.append({
            'months': years * 12,
            'text': f"{years} {_russian_year_label(years)}",
            'pos': m.start()
        })
        age_patterns.append({
            'months': months,
            'text': f"{months} {_russian_month_label(months)}",
            'pos': m.start()
        })
        processed_positions.add(m.start())
    
    # Ищем простые возраста в годах
    for m in re.finditer(r'(\d+)\s*(?:лет|год(?:а|ов)?|г\.?)', text_lower):
        if m.start() not in processed_positions:
            years = int(m.group(1))
            months = years * 12
            age_patterns.append({
                'months': months,
                'text': f"{years} {_russian_year_label(years)}",
                'pos': m.start()
            })
            processed_positions.add(m.start())
    
    # Ищем возраста в месяцах
    for m in re.finditer(r'(\d+)\s*(?:месяц(?:а|ев)?|мес\.?)', text_lower):
        if m.start() not in processed_positions:
            months = int(m.group(1))
            age_patterns.append({
                'months': months,
                'text': f"{months} {_russian_month_label(months)}",
                'pos': m.start()
            })
            processed_positions.add(m.start())
    
    # Убираем дубликаты по позиции
    age_patterns = [age for i, age in enumerate(age_patterns) if not any(a['pos'] == age['pos'] for a in age_patterns[:i])]
    
    # Распределяем возраста по детям
    if age_patterns:
        if expected_children > len(age_patterns) and expected_children > 0:
            extended_ages = []
            for i in range(expected_children):
                age_idx = i % len(age_patterns)
                extended_ages.append(age_patterns[age_idx])
            age_patterns = extended_ages
        
        for age in age_patterns[:expected_children if expected_children > 0 else len(age_patterns)]:
            data['children'].append(age['months'])
            data['children_original'].append(age['text'])
    elif expected_children > 0:
        for _ in range(expected_children):
            data['children'].append(0)
            data['children_original'].append('возраст не указан')

    # ========== 4. ОБРАБОТКА ВЗРОСЛЫХ ==========
    for num_info in all_numbers:
        if num_info['pos'] in processed_positions:
            continue
            
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
        
    # ========== 4. ОБРАБОТКА ВЗРОСЛЫХ ==========
    for num_info in all_numbers:
        if num_info['pos'] in processed_positions:
            continue
            
        num = num_info['value']
        pos = num_info['pos']
        t_idx = _find_token_index_for_pos(pos)

        left_context = tokens[t_idx-1]['text'] if t_idx is not None and t_idx-1 >= 0 else ''
        right_context = tokens[t_idx+1]['text'] if t_idx is not None and t_idx+1 < len(tokens) else ''

        # Проверяем паттерны "нас/мы + число" для общего количества людей
        if left_context in ['нас', 'мы'] and right_context not in ['ребен', 'дет', 'детей', 'ребён', 'ребенка']:
            # Для "нас X" - это общее количество людей
            total_people = num
            # Вычитаем детей
            child_count = len(data['children']) if data['children'] else 0
            if child_count > 0 and total_people > child_count:
                data['adults'] = total_people - child_count
            else:
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

    # Беременность ВСЕГДА должна быть указана из-за строгих ограничений
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