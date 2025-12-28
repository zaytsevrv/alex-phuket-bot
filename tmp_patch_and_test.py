import re
import bot

# Новая реализация парсера (не меняя bot.py на диске) — временно заменим в рантайме
def parse_user_response_patched(text):
    text_lower = text.lower() if text else ""
    data = {
        'adults': 0,
        'children': [],
        'children_original': [],
        'pregnant': None,
        'priorities': [],
        'health_issues': [],
        'raw_text': text
    }

    missing_points = []

    number_words = {
        'один': 1, 'одного': 1, 'одной': 1,
        'два': 2, 'двое': 2, 'двух': 2,
        'три': 3, 'трое': 3, 'трёх': 3, 'трех': 3,
        'четыре': 4, 'четверо': 4, 'четверых': 4,
        'пять': 5, 'пятеро': 5,
        'шесть': 6, 'шестеро': 6,
        'семь': 7, 'семеро': 7,
        'восемь': 8, 'восьмеро': 8,
        'девять': 9, 'девятеро': 9,
        'десять': 10
    }

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

    # Найти числа
    all_numbers = []
    for m in re.finditer(r'(\d+)(?=\D|$)', text_lower):
        all_numbers.append({'value': int(m.group(1)), 'pos': m.start(), 'len': len(m.group(1)), 'type': 'digit'})
    for word, num in number_words.items():
        for m in re.finditer(r'\b' + re.escape(word) + r'\b', text_lower):
            all_numbers.append({'value': num, 'pos': m.start(), 'len': len(word), 'type': 'word', 'word': word})
    all_numbers.sort(key=lambda x: x['pos'])

    tokens = []
    for m in re.finditer(r'\b\w+\b', text_lower):
        tokens.append({'text': m.group(0), 'start': m.start(), 'end': m.end()})

    def _find_token_index_for_pos(p):
        for i, t in enumerate(tokens):
            if t['start'] <= p < t['end']:
                return i
        best = None
        best_dist = None
        for i, t in enumerate(tokens):
            dist = min(abs(t['start'] - p), abs(t['end'] - p))
            if best is None or dist < best_dist:
                best = i
                best_dist = dist
        return best

    for num_info in all_numbers:
        num = num_info['value']
        pos = num_info['pos']
        t_idx = _find_token_index_for_pos(pos)
        left_context = tokens[t_idx-1]['text'] if t_idx is not None and t_idx-1 >= 0 else ''
        right_context = tokens[t_idx+1]['text'] if t_idx is not None and t_idx+1 < len(tokens) else ''

        if any(k in left_context or k in right_context for k in ['взросл', 'взр']):
            if data['adults'] == 0:
                data['adults'] = num
            continue

        if any(k in left_context or k in right_context for k in ['ребен', 'дет', 'детей', 'ребён', 'ребенка']) or \
           any(k in right_context for k in ['лет', 'год', 'г', 'мес', 'месяц']):

            start = max(0, t_idx - 5)
            end = min(len(tokens), t_idx + 6)
            context_phrase = ' '.join(t['text'] for t in tokens[start:end])

            age_match = re.search(r'(\d+)\s*(?:лет|год(?:а|ов)?|г\.?)+\s*(?:и\s*)?(\d+)?\s*(?:месяц(?:а|ев)?|мес\.?)+', context_phrase)
            if age_match:
                years = int(age_match.group(1))
                months = int(age_match.group(2)) if age_match.group(2) else 0
                total_months = years * 12 + months
                if total_months not in data['children']:
                    data['children'].append(total_months)
                    if months == 0:
                        data['children_original'].append(f"{years} {_russian_year_label(years)}")
                    else:
                        data['children_original'].append(f"{years} {_russian_year_label(years)} и {months} {_russian_month_label(months)}")
                continue

            if any(k in context_phrase for k in ['лет', 'год', 'г.']):
                months = bot.age_to_months(f"{num} лет")
                if months > 0 and months not in data['children']:
                    data['children'].append(months)
                    data['children_original'].append(f"{num} {_russian_year_label(num)}")
                continue

            if any(k in context_phrase for k in ['месяц', 'мес']):
                months = int(num)
                if 0 < months < 216 and months not in data['children']:
                    data['children'].append(months)
                    data['children_original'].append(f"{months} {_russian_month_label(months)}")
                continue

            if any(k in context_phrase for k in ['ребен', 'дет', 'детей']):
                data['children'].append(0)
                data['children_original'].append('количество')
                continue

    # беременность
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

    # приоритеты
    priority_keywords = {
        'комфорт': ['комфорт', 'удобств', 'плавн', 'мягк'],
        'бюджет': ['бюджет', 'дешев', 'эконом', 'недорог'],
        'фотографии': ['фото', 'сним', 'инстаграм', 'красив'],
        'не рано вставать': ['не рано', 'поспать', 'поздн', 'не люблю рано', 'не хочу рано'],
    }
    for priority, keywords in priority_keywords.items():
        for keyword in keywords:
            if keyword in text_lower and priority not in data['priorities']:
                data['priorities'].append(priority)
                break

    health_keywords = {
        'спина': ['спин', 'поясниц'],
        'укачивание': ['укачиван', 'морск', 'тошн'],
        'ходьба': ['ходьб', 'ходить трудн', 'ноги болят'],
    }
    for issue, keywords in health_keywords.items():
        for keyword in keywords:
            if keyword in text_lower and issue not in data['health_issues']:
                data['health_issues'].append(issue)
                break

    # проверки
    if data['adults'] == 0:
        missing_points.append("количество взрослых")
    if data['pregnant'] is None:
        missing_points.append("беременность (да/нет)")
    child_keywords = ['ребен', 'дет', 'малыш', 'младш', 'сын', 'доч']
    if any(keyword in text_lower for keyword in child_keywords):
        if not data['children'] and 'без детей' not in text_lower and 'нет детей' not in text_lower:
            missing_points.append("информация о детях")
    elif data['adults'] > 0:
        missing_points.append("информация о детях")

    # синхронная обработка пар
    pairs = list(zip(data['children'], data['children_original']))
    if any(age > 0 for age, _ in pairs) and any(age == 0 for age, _ in pairs):
        pairs = [p for p in pairs if p[0] != 0]
    seen = set()
    new_pairs = []
    for age, orig in pairs:
        if age not in seen:
            seen.add(age)
            new_pairs.append((age, orig))
    if new_pairs:
        data['children'], data['children_original'] = zip(*new_pairs)
        data['children'] = list(data['children'])
        data['children_original'] = list(data['children_original'])
    else:
        data['children'] = []
        data['children_original'] = []

    return data, missing_points

# Патчим функцию в модуле bot
bot.parse_user_response = parse_user_response_patched

if __name__ == '__main__':
    test_text = "Нас двое и с нами двое детей 7 лет и 10 месяцев. Я беременная."
    parsed, missing = bot.parse_user_response(test_text)
    print('PARSED:', parsed)
    print('MISSING:', missing)

    # Фильтрация туров по безопасности
    safe = bot.filter_tours_by_safety(bot.TOURS, parsed)
    print('SAFE COUNT:', len(safe))
    if safe:
        ranked = bot.rank_tours_by_priorities(safe, parsed)
        print('TOP SAFE NAMES:', [t.get('Название') for t in ranked[:5]])
    else:
        print('NO SAFE TOURS FOUND')
