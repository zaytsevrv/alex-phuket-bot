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

    # ========== 2. НАХОДИМ ВСЕ ЧИСЛА И ЧИСЛИТЕЛЬНЫЕ В ТЕКСТЕ (СТРОГО) ==========
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

    # Токенизируем текст (только слова и цифры) с позициями
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

    current_child_count = 1  # текущий счетчик количества детей для следующих возрастов

    for num_info in all_numbers:
        num = num_info['value']
        pos = num_info['pos']
        t_idx = _find_token_index_for_pos(pos)

        left_context = tokens[t_idx-1]['text'] if t_idx is not None and t_idx-1 >= 0 else ''
        right_context = tokens[t_idx+1]['text'] if t_idx is not None and t_idx+1 < len(tokens) else ''

        # Если контекст явно говорит про взрослых
        if any(k in left_context or k in right_context for k in ['взросл', 'взр']):
            if data['adults'] == 0:
                data['adults'] = num
            continue
        
        # Проверяем паттерны "нас/мы + число" для взрослых
        if left_context in ['нас', 'мы'] and right_context not in ['ребен', 'дет', 'детей', 'ребён', 'ребенка']:
            if data['adults'] == 0:
                data['adults'] = num
            continue
        
        # Если число явно указывает количество детей (перед "дети", "ребенок")
        if right_context in ['ребен', 'дет', 'детей', 'ребён', 'ребенка']:
            current_child_count = num
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
                
                # Проверяем, есть ли указание количества детей перед этим
                child_count = 1  # по умолчанию 1 ребенок
                for prev_num in all_numbers:
                    if prev_num['pos'] < pos and prev_num['value'] <= 10:  # число перед текущим
                        prev_t_idx = _find_token_index_for_pos(prev_num['pos'])
                        if prev_t_idx is not None:
                            prev_start = max(0, prev_t_idx - 2)
                            prev_end = min(len(tokens), prev_t_idx + 3)
                            prev_context = ' '.join(t['text'] for t in tokens[prev_start:prev_end])
                            if any(k in prev_context for k in ['ребен', 'дет', 'детей']) and not any(k in prev_context for k in ['взросл', 'взр']):
                                child_count = prev_num['value']
                                break
                
                # Добавляем соответствующее количество детей с этим возрастом
                for _ in range(current_child_count):
                    data['children'].append(total_months)
                    # Формируем человекочитаемый текст
                    if months == 0:
                        data['children_original'].append(f"{years} {_russian_year_label(years)}")
                    else:
                        data['children_original'].append(f"{years} {_russian_year_label(years)} и {months} {_russian_month_label(months)}")
                current_child_count = 1  # сбрасываем
                continue

            # Если указано в годах
            if any(k in right_context for k in ['лет', 'год', 'г.']):
                months = age_to_months(f"{num} лет")
                if months > 0:
                    for _ in range(current_child_count):
                        data['children'].append(months)
                        data['children_original'].append(f"{num} {_russian_year_label(num)}")
                    current_child_count = 1
                continue

            # Если указано в месяцах
            if any(k in right_context for k in ['месяц', 'мес']):
                months = int(num)
                if 0 < months < 216:
                    for _ in range(current_child_count):
                        data['children'].append(months)
                        data['children_original'].append(f"{months} {_russian_month_label(months)}")
                    current_child_count = 1
                continue

            # Если рядом слово 'ребен'/'дет' и нет единиц измерения — это количество детей (маркер)
            if any(k in context_phrase for k in ['ребен', 'дет', 'детей']):
                # добавляем маркер 0 (возраст не указан)
                data['children'].append(0)
                data['children_original'].append('количество')
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