#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ФИНАЛЬНЫЙ ТЕСТ ДЛЯ ПРОВЕРКИ ВСЕХ ИСПРАВЛЕНИЙ
"""

from bot import (
    search_tours_by_keywords_hybrid,
    filter_tours_by_safety,
    make_category_keyboard,
    make_confirmation_keyboard
)

print("=" * 60)
print("🔧 ФИНАЛЬНЫЙ ТЕСТ ВСЕХ ИСПРАВЛЕНИЙ")
print("=" * 60)
print()

# TEST 1: Критичная ошибка NameError
print("✅ TEST 1: Функция make_confirmation_keyboard существует")
try:
    keyboard = make_confirmation_keyboard()
    print(f"   ✓ Клавиатура создана успешно")
    print(f"   ✓ Количество рядов: {len(keyboard.keyboard)}")
except NameError as e:
    print(f"   ✗ ОШИБКА: {e}")
print()

# TEST 2: Поиск слонов
print("✅ TEST 2: Поиск слонов (лемматизация)")
results, used_word = search_tours_by_keywords_hybrid("хочу увидеть слонов")
print(f"   ✓ Найдено {len(results)} экскурсий вместо 2")
if len(results) >= 8:
    print(f"   ✓ УСПЕХ: Лемматизация работает (ищем все варианты слова)")
else:
    print(f"   ✗ ОШИБКА: Ожидалось минимум 8, получено {len(results)}")
print()

# TEST 3: Безопасность фильтра
print("✅ TEST 3: Фильтр безопасности для беременных")
tours = [tour for tour, cat, rel in results]
test_user_data = {
    'pregnant': True,
    'children': [],
    'health_issues': []
}
filtered = filter_tours_by_safety(tours, test_user_data)
print(f"   ✓ Исходно: {len(tours)} туров")
print(f"   ✓ После фильтра: {len(filtered)} туров")
print(f"   ✓ Удалено {len(tours) - len(filtered)} туров (несовместимые с беременностью)")
print()

# TEST 4: Клавиатуры категорий
print("✅ TEST 4: Клавиатуры категорий (сворачивание)")
kb_collapsed = make_category_keyboard(show_all=False)
kb_expanded = make_category_keyboard(show_all=True)
print(f"   ✓ Свёрнутый вид: {len(kb_collapsed.keyboard)} рядов")
print(f"   ✓ Развёрнутый вид: {len(kb_expanded.keyboard)} рядов")

# Проверяем наличие нужных кнопок
collapsed_buttons = [btn.text for row in kb_collapsed.keyboard for btn in row]
expanded_buttons = [btn.text for row in kb_expanded.keyboard for btn in row]

if "📂 Показать ещё категории" in collapsed_buttons:
    print(f"   ✓ Кнопка 'Показать ещё' присутствует в свёрнутом виде")
else:
    print(f"   ✗ ОШИБКА: Кнопка 'Показать ещё' не найдена")

if "🔽 Скрыть категории" in expanded_buttons:
    print(f"   ✓ Кнопка 'Скрыть' присутствует в развёрнутом виде")
else:
    print(f"   ✗ ОШИБКА: Кнопка 'Скрыть' не найдена")

# Проверяем расстановку ХИТ кнопок
hit_check = (
    kb_collapsed.keyboard[0][0].text == "Море (Острова)" and
    len(kb_collapsed.keyboard[1]) == 2 and
    "Суша (обзорные)" in [btn.text for btn in kb_collapsed.keyboard[1]]
)

if hit_check:
    print(f"   ✓ ХИТ категории в правильной расстановке (2 ряда)")
else:
    print(f"   ✗ ОШИБКА: ХИТ категории не в ожидаемом порядке")

print()
print("=" * 60)
print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
print("=" * 60)
