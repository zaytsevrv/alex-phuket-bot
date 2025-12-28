#!/usr/bin/env python3
"""
КОМПЛЕКСНЫЙ ТЕСТ: Проверяем что гибридный поиск работает для фраз
и что кнопка "Новый поиск" присутствует в меню категорий.
"""

import pandas as pd
from difflib import get_close_matches

# Загружаем CSV
df = pd.read_csv('Price22.12.2025.csv', sep=';', encoding='utf-8-sig')
TOURS = df.to_dict('records')

def get_categories():
    """Получает все категории из CSV"""
    categories = df['Для информации'].unique().tolist()
    return sorted([c for c in categories if pd.notna(c)])

def search_tours_by_keywords(query):
    """Поиск туров по ключевому слову"""
    query_lower = query.lower().strip()
    if not query_lower:
        return []
    results = []
    for tour in TOURS:
        relevance = 0
        tour_name = tour.get('Название', '').lower()
        if query_lower in tour_name:
            relevance += 100
        keywords = tour.get('Ключевые слова', '')
        if keywords:
            keywords_lower = str(keywords).lower()
            if query_lower in keywords_lower:
                relevance += 50
        description = tour.get('Описание (Витрина)', '')
        if description:
            description_lower = str(description).lower()
            if query_lower in description_lower:
                relevance += 30
        review = tour.get('Честный обзор', '')
        if review:
            review_lower = str(review).lower()
            if query_lower in review_lower:
                relevance += 20
        if relevance > 0:
            category = tour.get('Для информации', 'Неизвестная категория')
            results.append((tour, category, relevance))
    results.sort(key=lambda x: x[2], reverse=True)
    return results

def search_tours_by_keywords_hybrid(query):
    """Гибридный поиск (из bot.py)"""
    results = search_tours_by_keywords(query)
    if results:
        return results, query
    
    words = query.lower().split()
    stop_words = {'хочу', 'давайте', 'укажите', 'ответьте', 'посоветуйте',
                  'что', 'как', 'где', 'когда', 'приложить', 'пожалуйста',
                  'буду', 'нужна', 'нужны', 'можно', 'есть', 'все', 'если',
                  'про', 'рассказать', 'ищу', 'посмотреть', 'увидеть', 'видеть',
                  'показать', 'узнать', 'расскажи'}
    
    content_words = [w for w in words if len(w) > 3 and w not in stop_words]
    content_words.sort(key=len, reverse=True)
    
    for word in content_words:
        results = search_tours_by_keywords(word)
        if results:
            return results, word
    
    return [], query

def make_category_keyboard():
    """Создает клавиатуру с категориями (из bot.py)"""
    categories = get_categories()
    
    hit_categories = [
        "Море (Острова)",
        "Суша (семейные)",
        "Суша (обзорные)"
    ]
    
    keyboard = []
    
    for cat in categories:
        if cat in hit_categories:
            keyboard.append([cat])
    
    remaining_cats = [c for c in categories if c not in hit_categories]
    
    for i in range(0, len(remaining_cats), 2):
        row = remaining_cats[i:i+2]
        keyboard.append(row)
    
    keyboard.append(["🔄 Новый поиск"])
    
    return keyboard

print("=" * 70)
print("🧪 КОМПЛЕКСНЫЙ ТЕСТ: Гибридный поиск + Меню категорий")
print("=" * 70)

# ТЕСТ 1: Гибридный поиск
print("\n📌 ТЕСТ 1: Гибридный поиск для фраз")
print("-" * 70)

test_queries = [
    ("хочу увидеть слонов", 2, "туры про слонов"),
    ("посоветуйте тур с животными", 1, "туры с животными"),
    ("рафтинг", 1, "туры с рафтингом"),
]

search_passed = 0
search_failed = 0

for query, min_count, description in test_queries:
    results, normalized = search_tours_by_keywords_hybrid(query)
    if len(results) >= min_count:
        print(f"✅ '{query}'")
        print(f"   Найдено: {len(results)} туров ({description})")
        print(f"   Нормализованный запрос: '{normalized}'")
        search_passed += 1
    else:
        print(f"❌ '{query}'")
        print(f"   ❌ Найдено только {len(results)} туров (ожидали ≥ {min_count})")
        search_failed += 1

print(f"\n   Результаты поиска: {search_passed}✅ {search_failed}❌")

# ТЕСТ 2: Меню категорий
print("\n📌 ТЕСТ 2: Меню категорий")
print("-" * 70)

keyboard = make_category_keyboard()
keyboard_flat = str(keyboard)

has_new_search = any("🔄 Новый поиск" in str(row) for row in keyboard)
has_hit_categories = (
    any("Море (Острова)" in str(row) for row in keyboard) and
    any("Суша (семейные)" in str(row) for row in keyboard) and
    any("Суша (обзорные)" in str(row) for row in keyboard)
)

menu_passed = 0
menu_failed = 0

print(f"Всего кнопок в меню: {len(keyboard)}")
print(f"Структура меню:")

for i, row in enumerate(keyboard, 1):
    print(f"  {i}. {row}")

if has_new_search:
    print(f"\n✅ Кнопка '🔄 Новый поиск' присутствует")
    menu_passed += 1
else:
    print(f"\n❌ Кнопка '🔄 Новый поиск' НЕ найдена!")
    menu_failed += 1

if has_hit_categories:
    print(f"✅ ХИТ категории присутствуют (Море, Суша семейные, Суша обзорные)")
    menu_passed += 1
else:
    print(f"❌ ХИТ категории отсутствуют!")
    menu_failed += 1

print(f"\n   Результаты меню: {menu_passed}✅ {menu_failed}❌")

# ИТОГОВЫЙ РЕЗУЛЬТАТ
print("\n" + "=" * 70)
total_passed = search_passed + menu_passed
total_failed = search_failed + menu_failed
print(f"🎯 ИТОГО: {total_passed}✅ {total_failed}❌")

if total_failed == 0:
    print("🎉 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
    print("\n✨ Бот готов к тестированию пользователем:")
    print("   • Гибридный поиск работает для фраз вроде 'хочу увидеть слонов'")
    print("   • Кнопка 'Новый поиск' присутствует в меню")
    print("   • ХИТ категории отображаются отдельно")
else:
    print(f"\n⚠️  Найдены проблемы - нужно исправить")

print("=" * 70)
