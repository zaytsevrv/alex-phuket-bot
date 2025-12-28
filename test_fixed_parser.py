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
    """СТРОГАЯ фильтрация экскурсий по тегам безопасности из CSV.
    Основывается ТОЛЬКО на столбце "Теги (Безопасность)".
    """
    filtered_tours = []
    
    for tour in tours:
        is_safe = True
        tags = tour.get("Теги (Безопасность)", "").lower()
        
        # === 1. ПРОВЕРКА ДЛЯ БЕРЕМЕННЫХ ===
        if pregnant:
            if "#нельзя_беременным" in tags:
                is_safe = False
            elif "#можно_беременным" not in tags and "#можно_всем" not in tags:
                # Если нет явного разрешения для беременных - по умолчанию нельзя
                is_safe = False
        
        # === 2. ПРОВЕРКА ВОЗРАСТА ДЕТЕЙ ===
        if children_ages:
            # Проверяем каждого ребенка на соответствие возрастным ограничениям
            for age_months in children_ages:
                child_safe = True
                
                # Если ребенок до 1 года (12 месяцев)
                if age_months < 12:
                    if "#дети_от_1_года" in tags or "#от_18_лет" in tags or "#дети_от_2_лет" in tags or \
                       "#дети_от_3_лет" in tags or "#дети_от_4_лет" in tags or "#дети_от_7_лет" in tags or \
                       "#дети_от_12_лет" in tags:
                        child_safe = False
                    elif "#можно_детям" not in tags and "#можно_всем" not in tags:
                        # По умолчанию - если нет явного разрешения для детей
                        child_safe = False
                
                # Проверка по конкретным возрастным ограничениям
                elif 12 <= age_months < 24:  # 1-2 года
                    if "#дети_от_2_лет" in tags or "#дети_от_3_лет" in tags or \
                       "#дети_от_4_лет" in tags or "#дети_от_7_лет" in tags or \
                       "#дети_от_12_лет" in tags or "#от_18_лет" in tags:
                        child_safe = False
                
                elif 24 <= age_months < 36:  # 2-3 года
                    if "#дети_от_3_лет" in tags or "#дети_от_4_лет" in tags or \
                       "#дети_от_7_лет" in tags or "#дети_от_12_лет" in tags or \
                       "#от_18_лет" in tags:
                        child_safe = False
                
                elif 36 <= age_months < 48:  # 3-4 года
                    if "#дети_от_4_лет" in tags or "#дети_от_7_лет" in tags or \
                       "#дети_от_12_лет" in tags or "#от_18_лет" in tags:
                        child_safe = False
                
                elif 48 <= age_months < 84:  # 4-7 лет
                    if "#дети_от_7_лет" in tags or "#дети_от_12_лет" in tags or \
                       "#от_18_лет" in tags:
                        child_safe = False
                
                elif 84 <= age_months < 144:  # 7-12 лет
                    if "#дети_от_12_лет" in tags or "#от_18_лет" in tags:
                        child_safe = False
                
                elif 144 <= age_months < 216:  # 12-18 лет
                    if "#от_18_лет" in tags:
                        child_safe = False
                
                # Если хотя бы один ребенок не подходит - вся экскурсия не подходит
                if not child_safe:
                    is_safe = False
                    break
        
        # === 3. ЕСЛИ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ - ДОБАВЛЯЕМ ===
        if is_safe:
            filtered_tours.append(tour)
    
    return filtered_tours

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
            
            # Показываем сводку для подтверждения
            summary = pf.generate_confirmation_summary(data)
            print(f"  Сводка для подтверждения:\n{summary}")
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
    sea_tours = [t for t in filtered_tours if 'море' in t.get('Для информации', '').lower() or 'острова' in t.get('Для информации', '').lower() or 'рыбалка' in t.get('Для информации', '').lower() or 'яхты' in t.get('Для информации', '').lower() or 'катера' in t.get('Для информации', '').lower()]
    print(f"\nМорских туров в результате: {len(sea_tours)} (должно быть 0)")

if __name__ == "__main__":
    test_parse_user_response()
    test_tour_filtering()