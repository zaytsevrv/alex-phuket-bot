#!/usr/bin/env python3
"""
Тест гибридного поиска для фраз со стоп-словами.
Проверяет что "хочу увидеть слонов" находит туры про слонов.
"""

import pandas as pd
from difflib import get_close_matches

# Загружаем CSV
df = pd.read_csv('Price22.12.2025.csv', sep=';', encoding='utf-8-sig')
TOURS = df.to_dict('records')

def search_tours_by_keywords(query):
    """Ищет туры по ключевому слову"""
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
    """ГИБРИДНЫЙ ПОИСК с нормализацией"""
    # Шаг 1: Точный поиск по всей фразе
    results = search_tours_by_keywords(query)
    if results:
        return results, query
    
    # Шаг 2: Поиск в отдельных словах фразы (с отсеиванием стоп-слов)
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
    
    # Шаг 3: Размытый поиск (difflib)
    all_searchable = set()
    
    for tour in TOURS:
        name = tour.get('Название', '').lower()
        keywords = str(tour.get('Ключевые слова', '')).lower()
        description = str(tour.get('Описание (Витрина)', '')).lower()
        
        if name:
            all_searchable.add(name)
        if keywords:
            all_searchable.add(keywords)
        
        for word in description.split():
            if len(word) > 3:
                all_searchable.add(word)
    
    close_matches = get_close_matches(query.lower(), list(all_searchable), n=3, cutoff=0.8)
    
    if close_matches:
        for match in close_matches:
            results = search_tours_by_keywords(match)
            if results:
                return results, match
    
    for word in words:
        if len(word) > 3:
            close = get_close_matches(word, list(all_searchable), n=1, cutoff=0.8)
            if close:
                results = search_tours_by_keywords(close[0])
                if results:
                    return results, close[0]
    
    return [], query

# === ТЕСТЫ ===

print("=" * 70)
print("🧪 ТЕСТ: Гибридный поиск для фраз со стоп-словами")
print("=" * 70)

tests = [
    ("хочу увидеть слонов", 2, "ГЛАВНЫЙ ТЕСТ: должны найтись туры про слонов"),
    ("рафтинг", 1, "Точный поиск - туры с рафтингом"),
    ("слоны", 2, "Поиск слонов (разные словоформы)"),
]

passed = 0
failed = 0

for query, min_expected, description in tests:
    results, normalized = search_tours_by_keywords_hybrid(query)
    
    count_ok = len(results) >= min_expected
    
    if count_ok:
        print(f"✅ '{query}'")
        print(f"   {description}")
        print(f"   Найдено: {len(results)} туров, нормализованный запрос: '{normalized}'")
        if results:
            print(f"   Примеры: {', '.join([r[0].get('Название')[:30] for r in results[:2]])}")
        passed += 1
    else:
        print(f"❌ '{query}'")
        print(f"   {description}")
        print(f"   ❌ Найдено только {len(results)} туров (ожидали ≥ {min_expected})")
        print(f"   Нормализованный запрос: '{normalized}'")
        failed += 1
    print()

print("=" * 70)
print(f"Результаты: {passed}✅ {failed}❌")
if failed == 0:
    print("🎉 ВСЕ ТЕСТЫ ПРОШЛИ!")
print("=" * 70)
