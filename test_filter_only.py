#!/usr/bin/env python3
"""
Простой тест фильтрации туров без импорта всего бота
"""
import csv

def load_tours(filename):
    """Загружаем туры из CSV"""
    tours = []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                tours.append(row)
    except Exception as e:
        print(f"Ошибка загрузки туров: {e}")
    return tours

def filter_tours_by_safety(tours, user_data):
    """
    СТРОГАЯ фильтрация экскурсий по тегам безопасности из CSV.
    Основывается ТОЛЬКО на столбце "Теги (Безопасность)".
    """
    filtered_tours = []

    is_pregnant = user_data.get('pregnant', False)
    children_ages = user_data.get('children', [])  # возрасты в месяцах

    for tour in tours:
        is_safe = True
        tags = tour.get("Теги (Безопасность)", "").lower()

        # === 1. ПРОВЕРКА ДЛЯ БЕРЕМЕННЫХ ===
        if is_pregnant:
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

if __name__ == "__main__":
    # Загружаем туры
    tours = load_tours('Price22.12.2025.csv')
    print(f"Загружено {len(tours)} туров")

    # Тест фильтрации для беременной с детьми 7 лет
    user_data = {'pregnant': True, 'children': [94, 94]}  # 7 лет 10 месяцев
    filtered = filter_tours_by_safety(tours, user_data)
    print(f"Безопасных туров для беременной с детьми 7 лет: {len(filtered)}")

    # Показываем первые 3
    print("\nПервые 3 безопасных тура:")
    for i, tour in enumerate(filtered[:3], 1):
        print(f"{i}. {tour.get('Название', 'Без названия')}")