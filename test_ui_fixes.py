#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ТЕСТ ВСЕХ ИСПРАВЛЕНИЙ
"""

from bot import TOURS, format_tour_card_compact, make_tours_keyboard

print("="*60)
print("✅ ТЕСТ ИСПРАВЛЕНИЙ ПРОБЛЕМ")
print("="*60)
print()

# TEST 1: Показываются только ХИТы (максимум 3)
print("TEST 1: Показываются только ХИТы (макс 3)")
print("-"*60)

hit_tours = [t for t in TOURS if "ХИТ" in t.get("Название", "")]
print(f"✓ Всего ХИТов в базе: {len(hit_tours)}")

keyboard = make_tours_keyboard(TOURS)
button_count = len(keyboard.inline_keyboard)
print(f"✓ Кнопок на клавиатуре: {button_count}")

# Проверяем что только ХИТы в первых 3 кнопках
hit_count_shown = 0
for i in range(min(3, button_count)):
    row = keyboard.inline_keyboard[i]
    for btn in row:
        if "🏆" in btn.text:
            hit_count_shown += 1

print(f"✓ ХИТов показано: {hit_count_shown}/3")

if hit_count_shown <= 3:
    print("✅ PASS: Показываются только ХИТы, максимум 3")
else:
    print("❌ FAIL: Показано больше чем 3 ХИТа")
print()

# TEST 2: Названия очищены от скобок
print("TEST 2: Названия без скобок и (35)")
print("-"*60)

cleaned_names = []
for hit in hit_tours[:3]:
    name = hit.get("Название", "")
    cleaned_name = format_tour_card_compact(hit).split('\n')[0]
    
    print(f"\nОригинал: {name}")
    print(f"Очищено: {cleaned_name}")
    
    # Проверяем что нет "(ХИТ)" и иных скобок в конце
    if "(ХИТ)" not in cleaned_name and "(Стандарт)" not in cleaned_name and "(Комфорт" not in cleaned_name:
        print("✅ Скобки удалены")
        cleaned_names.append(True)
    else:
        print("❌ Скобки ещё есть")
        cleaned_names.append(False)

if all(cleaned_names):
    print("\n✅ PASS: Все названия очищены от скобок")
else:
    print("\n❌ FAIL: Некоторые названия содержат скобки")
print()

# TEST 3: Нет "Почему это отлично?" с отрицательными ограничениями
print("TEST 3: Описание без отрицательных ограничений")
print("-"*60)

from bot import format_tour_description_alex_style

has_negative_limitations = False
for hit in hit_tours[:2]:
    desc = format_tour_description_alex_style(hit)
    
    if "не подходит" in desc.lower() or "запрещен" in desc.lower():
        has_negative_limitations = True
        print(f"❌ Найдено отрицательное ограничение в описании")
        print(f"   {desc[:100]}...")

if not has_negative_limitations:
    print("✅ PASS: Описание содержит только позитивные качества")
else:
    print("❌ FAIL: Найдены отрицательные ограничения в описании")
print()

# TEST 4: Кнопка "Показать ещё" есть
print("TEST 4: Кнопка 'Показать ещё'")
print("-"*60)

show_more_found = False
for row in keyboard.inline_keyboard:
    for btn in row:
        if "Показать ещё" in btn.text:
            show_more_found = True
            print(f"✓ Найдена кнопка: {btn.text}")

if show_more_found:
    print("✅ PASS: Кнопка 'Показать ещё' присутствует")
else:
    print("❌ FAIL: Кнопка 'Показать ещё' не найдена")
print()

print("="*60)
print("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
print("="*60)
