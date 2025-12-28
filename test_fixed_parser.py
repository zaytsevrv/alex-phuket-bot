#!/usr/bin/env python3
"""
Тестирование исправленной функции parse_user_response
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import parser_functions as pf
import csv

def load_tours():
    """Загружаем туры из CSV"""
    tours = []
    try:
        with open('Price22.12.2025.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                tours.append(row)
    except Exception as e:
        print(f"Ошибка загрузки туров: {e}")
    return tours

def filter_tours_by_safety(tours, pregnant, children_ages):
    """Фильтруем туры по безопасности"""
    filtered = []

    for tour in tours:
        safety_tags = tour.get('Теги (Безопасность)', '').lower()

        # Исключаем морские туры для беременных и детей до 1 года
        if pregnant and ('море' in safety_tags or 'морск' in safety_tags):
            continue

        # Исключаем морские туры для детей младше 1 года
        if any(age < 12 for age in children_ages) and ('море' in safety_tags or 'морск' in safety_tags):
            continue

        filtered.append(tour)

    return filtered

def test_parse_user_response():
    """Тестируем парсер на различных примерах"""

    test_cases = [
        # Тестовый случай из задачи
        "Нас двое и с нами двое детей 7 лет и 10 месяцев. Я беременная.",

        # Другие тестовые случаи
        "Мы вдвоем с ребенком 3 года",
        "Нас трое взрослых и двое детей: 5 лет и 8 месяцев",
        "Я одна, беременная, без детей",
        "Двое взрослых, ребенок 2 года",
        "Нас четверо: двое взрослых и двое детей по 4 года",
        "Я с мужем и ребенком 6 месяцев",
        "Трое взрослых, беременная, дети 1 год и 3 года",
    ]

    print("=== ТЕСТИРОВАНИЕ ИСПРАВЛЕННОЙ ФУНКЦИИ PARSE_USER_RESPONSE ===\n")

    for i, test_text in enumerate(test_cases, 1):
        print(f"Тест {i}: {test_text}")
        try:
            data, missing = pf.parse_user_response(test_text)
            print(f"  Результат: adults={data['adults']}, children={data['children']}, pregnant={data['pregnant']}")
            if data['children_original']:
                print(f"  Возраста оригинал: {data['children_original']}")
            if missing:
                print(f"  Пропущено: {missing}")
            print()
        except Exception as e:
            print(f"  ОШИБКА: {e}\n")

def test_tour_filtering():
    """Тестируем фильтрацию туров для беременной с детьми"""
    print("=== ТЕСТИРОВАНИЕ ФИЛЬТРАЦИИ ТУРОВ ===\n")

    # Загружаем туры
    tours = load_tours()
    print(f"Загружено {len(tours)} туров")

    # Тестовый случай: беременная с детьми 7 лет и 10 месяцев
    test_text = "Нас двое и с нами двое детей 7 лет и 10 месяцев. Я беременная."
    data, _ = pf.parse_user_response(test_text)

    print(f"Парсинг: {test_text}")
    print(f"Результат: adults={data['adults']}, children={data['children']}, pregnant={data['pregnant']}")

    # Фильтруем туры
    filtered_tours = filter_tours_by_safety(tours, data['pregnant'], data['children'])
    print(f"\nОтфильтровано {len(filtered_tours)} безопасных туров")

    # Показываем первые 5
    print("\nПервые 5 безопасных туров:")
    for i, tour in enumerate(filtered_tours[:5], 1):
        print(f"{i}. {tour.get('Название', 'Без названия')}")

    # Проверяем, что морские туры исключены
    sea_tours = [t for t in filtered_tours if 'море' in t.get('Теги (Безопасность)', '').lower() or 'морск' in t.get('Теги (Безопасность)', '').lower()]
    print(f"\nМорских туров в результате: {len(sea_tours)} (должно быть 0)")

if __name__ == "__main__":
    test_parse_user_response()
    test_tour_filtering()