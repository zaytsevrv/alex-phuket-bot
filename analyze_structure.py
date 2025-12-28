# analyze_structure.py - проанализировать структуру бота
with open('bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

print("🔍 АНАЛИЗ СТРУКТУРЫ БОТА")
print("="*60)

# Ищем все async функции
import re
async_functions = re.findall(r'async def (\w+)', content)

print(f"📊 Найдено {len(async_functions)} async функций:")
for i, func in enumerate(async_functions[:15]):  # Покажем первые 15
    print(f"  {i+1}. {func}")

print(f"\n🔎 ПОИСК КЛЮЧЕВЫХ КОМПОНЕНТОВ:")

# 1. Поиск обработки экскурсий
tour_keywords = ['tour', 'экскурс', 'Название', 'Цена', 'Описание']
tour_functions = []
for func in async_functions:
    # Находим начало функции
    pattern = rf'async def {func}\(.*?\):(.*?)(?=async def|\Z)'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        func_body = match.group(1)
        if any(keyword in func_body for keyword in tour_keywords):
            tour_functions.append(func)

print(f"\n🎯 Функции обработки экскурсий: {tour_functions or 'Не найдены'}")

# 2. Поиск обработки FAQ
faq_keywords = ['faq', 'FAQ', 'вопрос', 'ответ', 'часто задаваем']
faq_functions = []
for func in async_functions:
    pattern = rf'async def {func}\(.*?\):(.*?)(?=async def|\Z)'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        func_body = match.group(1)
        if any(keyword in func_body.lower() for keyword in faq_keywords):
            faq_functions.append(func)

print(f"❓ Функции обработки FAQ: {faq_functions or 'Не найдены'}")

# 3. Поиск обработки данных
data_keywords = ['дети', 'ребенок', 'возраст', 'беремен', 'взросл']
data_functions = []
for func in async_functions:
    pattern = rf'async def {func}\(.*?\):(.*?)(?=async def|\Z)'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        func_body = match.group(1)
        if any(keyword in func_body.lower() for keyword in data_keywords):
            data_functions.append(func)

print(f"👨‍👩‍👧‍👦 Функции обработки данных: {data_functions or 'Не найдены'}")

print("\n" + "="*60)
print("📋 РЕКОМЕНДАЦИИ:")

if tour_functions:
    print(f"1. Добавьте аналитику в функцию: {tour_functions[0]}")
    print("   Код для вставки:")
    print('''
    # === АНАЛИТИКА: ПРОСМОТР ЭКСКУРСИИ ===
    user = update.effective_user  # или query.from_user
    track_user_session(context, BOT_STAGES['tour_details'])
    logger.log_action(user.id, "viewed_tour", stage=BOT_STAGES['tour_details'])
    context.user_data['last_action'] = 'tour_view'
    # === КОНЕЦ АНАЛИТИКИ ===
    ''')

if faq_functions:
    print(f"\n2. Добавьте аналитику в функцию: {faq_functions[0]}")
    print("   Код для вставки:")
    print('''
    # === АНАЛИТИКА: ВОПРОС В FAQ ===
    user = update.effective_user
    track_user_session(context, BOT_STAGES['faq'])
    logger.log_action(user.id, "asked_question", stage=BOT_STAGES['faq'])
    context.user_data['last_action'] = 'faq_question'
    # === КОНЕЦ АНАЛИТИКИ ===
    ''')

if not (tour_functions or faq_functions):
    print("1. Отправьте мне названия 3-5 функций из списка выше")
    print("2. Я скажу, в какие из них добавить аналитику")