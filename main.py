import asyncio
import json
import secrets
from collections import Counter
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Вспомогательные функции для форматирования ответов
def get_level_up_msg(new_score: int, old_score: int) -> str:
    if new_score >= 200 > old_score:
        return "\n\n👑 *НОВЫЙ УРОВЕНЬ: ЛЕГЕНДА!* 👑"
    elif new_score >= 100 > old_score:
        return "\n\n⭐ *НОВЫЙ УРОВЕНЬ: МАСТЕР!* ⭐"
    elif new_score >= 50 > old_score:
        return "\n\n🔍 *НОВЫЙ УРОВЕНЬ: ИССЛЕДОВАТЕЛЬ!* 🔍"
    return ""

def compose_success_response(reward: int, user: dict, explanation: str, level_up: str) -> str:
    res = f"{STATUS_EMOJIS['success']} *Отлично! Правильный ответ!*\n\n"
    res += f"➕ +{reward} очков\n"
    res += f"⭐ Всего очков: {user['score']}\n"
    if explanation:
        res += f"\n📖 *Объяснение:* {explanation}\n"
    res += level_up
    return res

def escape_markdown(text: str) -> str:
    """Экранирует спецсимволы для Telegram Markdown (версия 1)."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{c}' if c in escape_chars else c for c in text)

CATEGORY_EMOJIS = {
    "riddles": "🧩",
    "logic": "🧠",
    "javascript": "💻",
    "default": "📝"
}
DIFFICULTY_EMOJIS = {1: "🟢", 2: "🟡", 3: "🔴"}
DIFFICULTY_NAMES = {1: "Легко", 2: "Средне", 3: "Сложно"}
STATUS_EMOJIS = {
    "success": "✅", "error": "❌", "warning": "⚠️", "info": "ℹ️", "star": "⭐",
    "fire": "🔥", "trophy": "🏆", "medal": "🥇", "clock": "⏱️", "calendar": "📅",
    "gift": "🎁", "rocket": "🚀", "brain": "🧠", "bulb": "💡"
}

TOKEN = "8803174834:AAGVi-kTgn4RGx1WpcGJlkiTQJhILKGz89o"

USERS_FILE = "users.json"
users = {}


def load_users():
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {int(k): v for k, v in data.items()}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_users():
    global users
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def get_or_create_user(from_user):
    global users
    user_id = from_user.id
    if user_id in users:
        return users[user_id]
    user = {
        "id": user_id,
        "name": from_user.username if from_user.username else f"user_{user_id}",
        "score": 0,
        "tasks": [],
        "current_task": None,
        "last_bonus": None,
        "selected_categories": [],
        "hint_index": 0
    }
    users[user_id] = user
    save_users()
    return user


def load_tasks():
    try:
        with open("taskbot.txt", "r", encoding="utf-8") as file:
            content = file.read()
        try:
            data = json.loads(content)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
        return [line.strip() for line in content.splitlines() if line.strip() and not line.startswith('=')]
    except FileNotFoundError:
        print("Файл taskbot.txt не найден. Создаю тестовые задания.")
        return [
            {"id": 1, "category": "riddles", "difficulty": 1,
             "text": "Висит груша — нельзя скушать.",
             "answer": ["лампочка", "лампа"],
             "hints": ["Светит, но не солнце", "Вкручивают в потолок"],
             "explanation": "Лампочка формой похожа на грушу, горит, а не естся.",
             "time_limit": 120, "reward": 5},
            {"id": 2, "category": "logic", "difficulty": 2,
             "text": "Что можно приготовить, но нельзя съесть?",
             "answer": ["уроки", "домашнее задание"],
             "hints": ["Школьники этим заняты", "Задают в дневник"],
             "explanation": "Уроки готовят в учебном смысле, а не в кулинарном.",
             "time_limit": 150, "reward": 8},
        ]
    except UnicodeDecodeError:
        print("Ошибка кодировки. Попробуйте пересохранить файл в UTF-8.")
        return []


TASKS = load_tasks()


NO_CATEGORY = "Без категории"

def get_task_category(task):
    if isinstance(task, dict):
        return task.get("category", NO_CATEGORY) or NO_CATEGORY
    if isinstance(task, str):
        if "|" in task:
            category = task.split("|", 1)[0].strip()
            return category if category else NO_CATEGORY
        else:
            return NO_CATEGORY
    if isinstance(task, int):
        task_obj = next((item for item in TASKS if isinstance(item, dict) and item.get("id") == task), None)
        if task_obj:
            return task_obj.get("category", NO_CATEGORY) or NO_CATEGORY
        else:
            return NO_CATEGORY
    return NO_CATEGORY


def get_all_categories():
    cats = set()
    for task in TASKS:
        if isinstance(task, dict) and "category" in task:
            cats.add(task["category"])
    return sorted(cats)


def get_task_for_user(user):
    selected = user.get("selected_categories", [])
    if selected:
        available = [t for t in TASKS if isinstance(t, dict) and t.get("category") in selected]
    else:
        available = [t for t in TASKS if isinstance(t, dict)]
    if not available:
        return None
    day = datetime.now().day
    return available[(day - 1) % len(available)]


def format_task(task):
    if not isinstance(task, dict):
        return f"📝 {task}"
    category_emoji = CATEGORY_EMOJIS.get(task.get("category", ""), CATEGORY_EMOJIS["default"])
    difficulty_emoji = DIFFICULTY_EMOJIS.get(task.get("difficulty", 1), "🟢")
    difficulty_name = DIFFICULTY_NAMES.get(task.get("difficulty", 1), "Средне")
    text = f"{category_emoji} *Задание дня*\n\n"
    text += f"📌 *Текст:* {task['text']}\n\n"
    text += f"📊 *Сложность:* {difficulty_emoji} {difficulty_name}\n"
    text += f"⭐ *Награда:* {task.get('reward', 5)} очков\n"
    if "time_limit" in task:
        minutes = task["time_limit"] // 60
        seconds = task["time_limit"] % 60
        if minutes > 0:
            text += f"⏱️ *Время:* {minutes} мин {seconds} сек\n"
        else:
            text += f"⏱️ *Время:* {seconds} сек\n"
    if "hints" in task and task["hints"]:
        text += "\n💡 *Подсказки:*\n"
        for i, hint in enumerate(task["hints"], 1):
            text += f"  {i}. {hint}\n"
    return text


def format_user_stats(user):
    name = escape_markdown(user.get("name", "Пользователь"))
    score = user.get("score", 0)
    tasks_count = len(user.get("tasks", []))
    if score >= 200:
        level = "👑 Легенда"
        emoji = "👑"
    elif score >= 100:
        level = "⭐ Мастер"
        emoji = "⭐"
    elif score >= 50:
        level = "🔍 Исследователь"
        emoji = "🔍"
    else:
        level = "🌱 Новичок"
        emoji = "🌱"
    text = f"{emoji} *Профиль пользователя*\n\n"
    text += f"👤 *Имя:* {name}\n"
    text += f"📊 *Уровень:* {level}\n"
    text += f"⭐ *Очки:* {score}\n"
    text += f"📝 *Выполнено заданий:* {tasks_count}\n"
    category_counts = Counter(get_task_category(task) for task in user.get("tasks", []))
    if category_counts:
        text += "\n📊 *По категориям:*\n"
        for category, count in sorted(category_counts.items(), key=lambda item: (-item[1], item[0])):
            text += f"• {category}: {count}\n"
    if score < 50:
        next_level = 50
        progress = int((score / next_level) * 20)
        bar = "█" * progress + "░" * (20 - progress)
        text += "\n📈 *Прогресс до следующего уровня:*\n"
        text += f"`{bar}` {score}/{next_level}\n"
    return text


def format_task_history(history):
    text = "📜 *История выполненных заданий:*\n\n"
    for task in history[-10:]:
        if isinstance(task, dict):
            ttext = task.get("text", "Задание")
        elif isinstance(task, int):
            saved_task = next((item for item in TASKS if isinstance(item, dict) and item.get("id") == task), None)
            ttext = saved_task.get("text", f"Задание #{task}") if saved_task else f"Задание #{task}"
        else:
            ttext = str(task)
        text += f"• {ttext}\n"
    return text


def categories_keyboard(user_categories):
    all_cats = get_all_categories()
    keyboard = []
    for cat in all_cats:
        checked = "✅" if cat in user_categories else "⬜"
        emoji = CATEGORY_EMOJIS.get(cat, "📂")
        btn = InlineKeyboardButton(
            text=f"{checked} {emoji} {cat.capitalize()}",
            callback_data=f"cat_{cat}"
        )
        keyboard.append([btn])
    keyboard.append([InlineKeyboardButton(text="✅ Сохранить", callback_data="cat_save")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Задание дня", callback_data="get_task"),
            InlineKeyboardButton(text="💡 Подсказка", callback_data="hint")
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
            InlineKeyboardButton(text="🏆 Рейтинг", callback_data="leaderboard")
        ],
        [
            InlineKeyboardButton(text="🎁 Бонус", callback_data="daily_bonus"),
            InlineKeyboardButton(text="📂 Категории", callback_data="show_categories")
        ],
        [
            InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")
        ]
    ])
    return keyboard


async def cmd_start(message: types.Message):
    user = get_or_create_user(message.from_user)
    await message.answer(
    f"🎉 *Добро пожаловать в TaskBot!*\n\n"
    f"👋 Привет, {escape_markdown(user['name'])}!\n"
    f"Я помогу тебе развиваться с помощью ежедневных заданий.\n\n"
    f"🔹 Выполняй задания, получай очки и повышай уровень!\n"
    f"🔹 Используй кнопки ниже для навигации.",
    reply_markup=get_main_keyboard(),
    parse_mode="Markdown"
)
    today_task = get_task_for_user(user)
    if today_task:
        user["current_task"] = today_task
        user["hint_index"] = 0
        save_users()
        await message.answer(
            f"{STATUS_EMOJIS['info']} *Твое задание на сегодня:*\n\n"
            f"{format_task(today_task)}",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "😕 В выбранных категориях нет заданий.\n"
            "Измени настройки категорий или добавь новые задания.",
            reply_markup=get_main_keyboard()
        )


async def cmd_score(message: types.Message):
    user = get_or_create_user(message.from_user)
    await message.answer(
        format_user_stats(user),
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )


async def cmd_history_tasks(message: types.Message):
    user = get_or_create_user(message.from_user)
    history = user.get("tasks", [])
    if not history:
        await message.answer("📭 История выполненных заданий пока пуста.", reply_markup=get_main_keyboard())
        return
    await message.answer(format_task_history(history), parse_mode="Markdown", reply_markup=get_main_keyboard())


async def cmd_leaderboard(message: types.Message):
    global users
    if not users:
        await message.answer("😕 Пока нет пользователей в рейтинге!", reply_markup=get_main_keyboard())
        return
    sorted_users = sorted(users.values(), key=lambda x: x.get("score", 0), reverse=True)[:10]
    text = f"{STATUS_EMOJIS['trophy']} *Топ пользователей*\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, user_item in enumerate(sorted_users, 1):
        medal = medals[i - 1] if i <= 3 else f"{i}."
        name = escape_markdown(user_item.get("name", "Аноним"))
        score = user_item.get("score", 0)
        if score >= 200:
            level_emoji = "👑"
        elif score >= 100:
            level_emoji = "⭐"
        elif score >= 50:
            level_emoji = "🔍"
        else:
            level_emoji = "🌱"
        text += f"{medal} {level_emoji} *{name}* — {score} ⭐\n"
    user_id = message.from_user.id
    if user_id in users:
        user_score = users[user_id].get("score", 0)
        position = sum(1 for u in users.values() if u.get("score", 0) > user_score) + 1
        text += f"\n📊 *Твоя позиция:* {position} место"
        text += f"\n⭐ *Твои очки:* {user_score}"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard())


async def cmd_hint(message: types.Message):
    user = get_or_create_user(message.from_user)
    if not user.get("current_task"):
        await message.answer(
            "💡 У тебя нет активного задания!\n"
            "Используй /start чтобы получить задание.",
            reply_markup=get_main_keyboard()
        )
        return
    current_task = user["current_task"]
    if isinstance(current_task, dict) and "hints" in current_task:
        hints = current_task["hints"]
        hint_index = user.get("hint_index", 0)
        if hint_index < len(hints):
            await message.answer(
                f"💡 *Подсказка {hint_index + 1} из {len(hints)}*\n\n"
                f"{hints[hint_index]}",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard()
            )
            user["hint_index"] = hint_index + 1
            save_users()
        else:
            await message.answer(
                "😅 Подсказки закончились!\n"
                "Попробуй угадать самостоятельно.",
                reply_markup=get_main_keyboard()
            )
    else:
        await message.answer(
            "💡 Для этого задания нет подсказок.\n"
            "Попробуй ответить самостоятельно!",
            reply_markup=get_main_keyboard()
        )


async def cmd_daily_bonus(message: types.Message):
    user = get_or_create_user(message.from_user)
    today = datetime.now().date()
    last_bonus = user.get("last_bonus")
    if last_bonus and datetime.strptime(last_bonus, '%Y-%m-%d').date() == today:
        await message.answer(
            "🌅 *Ежедневный бонус уже получен!*\n\n"
            "Приходи завтра за новой порцией ☀️",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        return
    bonus = secrets.randbelow(11) + 5
    user["score"] += bonus
    user["last_bonus"] = today.isoformat()
    save_users()
    level_msg = ""
    if user["score"] >= 50 and user["score"] - bonus < 50:
        level_msg = "\n\n🎉 *Поздравляю! Ты достиг уровня* 🔍 *Исследователь!*"
    elif user["score"] >= 100 and user["score"] - bonus < 100:
        level_msg = "\n\n🎉 *Поздравляю! Ты достиг уровня* ⭐ *Мастер!*"
    elif user["score"] >= 200 and user["score"] - bonus < 200:
        level_msg = "\n\n👑 *Поздравляю! Ты достиг уровня* 👑 *Легенда!*"
    await message.answer(
        f"🎁 *Ежедневный бонус!*\n\n"
        f"➕ Ты получил {bonus} очков!\n"
        f"⭐ Всего очков: {user['score']}{level_msg}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )


async def cmd_help(message: types.Message):
    help_text = f"""
{STATUS_EMOJIS['info']} *Помощь по TaskBot*

*Основные команды:*
/start — 🎯 Получить задание дня
/score — 📊 Посмотреть статистику
/history — 📜 Посмотреть историю заданий
/help — ℹ️ Показать эту справку

*Кнопки быстрого доступа:*
📝 Задание дня — Получить новое задание
💡 Подсказка — Получить подсказку к заданию
📊 Статистика — Посмотреть свой прогресс
🏆 Рейтинг — Топ пользователей
🎁 Бонус — Получить ежедневный бонус
📂 Категории — Выбрать интересующие категории

*Как выполнять задания:*
1. Получи задание через /start
2. Напиши ответ в чат
3. Получи очки и поднимись в рейтинге!

*Уровни:*
🌱 Новичок — 0 очков
🔍 Исследователь — 50 очков
⭐ Мастер — 100 очков
👑 Легенда — 200 очков

💡 *Совет:* Чем быстрее ответишь, тем больше шансов на бонус!
"""
    await message.answer(help_text, parse_mode="Markdown", reply_markup=get_main_keyboard())


DEFAULT_CATEGORY = "Без категории"

# ---------- Вспомогательные функции (глобально) ----------
def get_level_up_msg(new_score: int, old_score: int) -> str:
    if new_score >= 200 > old_score:
        return "\n\n👑 *НОВЫЙ УРОВЕНЬ: ЛЕГЕНДА!* 👑"
    elif new_score >= 100 > old_score:
        return "\n\n⭐ *НОВЫЙ УРОВЕНЬ: МАСТЕР!* ⭐"
    elif new_score >= 50 > old_score:
        return "\n\n🔍 *НОВЫЙ УРОВЕНЬ: ИССЛЕДОВАТЕЛЬ!* 🔍"
    return ""

def compose_success_response(reward: int, user: dict, explanation: str, level_up: str) -> str:
    res = f"{STATUS_EMOJIS['success']} *Отлично! Правильный ответ!*\n\n"
    res += f"➕ +{reward} очков\n"
    res += f"⭐ Всего очков: {user['score']}\n"
    if explanation:
        res += f"\n📖 *Объяснение:* {explanation}\n"
    res += level_up
    return res

# ---------- Асинхронные обработчики ----------
async def process_correct_answer(user, current_task, message):
    reward = current_task.get("reward", 5)
    old_score = user["score"]
    user["score"] += reward
    user["tasks"].append(current_task.get("id", current_task))
    user["current_task"] = None
    user["hint_index"] = 0
    save_users()

    level_up = get_level_up_msg(user["score"], old_score)
    response = compose_success_response(reward, user, current_task.get("explanation", ""), level_up)
    await message.answer(response, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def process_incorrect_answer(user, current_task, message):   # <-- ОПРЕДЕЛЕНА ЗДЕСЬ
    hints = current_task.get("hints", [])
    used_hints = user.get("hint_index", 0)
    correct_answer = current_task["answer"][0] if current_task.get("answer") else ""

    remaining_hints = len(hints) - used_hints
    if remaining_hints <= 0 and hints:
        response = (f"{STATUS_EMOJIS['warning']} *Неправильно!*\n\n"
                    f"💡 Вот правильный ответ:\n`{correct_answer}`\n\n"
                    "Попробуй следующее задание через /start")
        user["current_task"] = None
        user["hint_index"] = 0
        save_users()
    else:
        response = f"{STATUS_EMOJIS['error']} *Неправильно!*\n\n"
        if remaining_hints > 0:
            response += f"💡 Осталось подсказок: {remaining_hints}\nИспользуй кнопку '💡 Подсказка'"
        else:
            response += "💡 Подсказки закончились!\nПопробуй еще раз или используй /start для нового задания"
    await message.answer(response, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def handle_dict_task(user, current_task, answer_text, message):
    correct_answers = [ans.lower() for ans in current_task.get("answer", [])]
    is_correct = any(answer_text == ans or ans in answer_text for ans in correct_answers)

    if is_correct:
        await process_correct_answer(user, current_task, message)
    else:
        await process_incorrect_answer(user, current_task, message)   # <-- ВЫЗОВ, ФУНКЦИЯ УЖЕ ОПРЕДЕЛЕНА

async def handle_string_task(user, current_task, answer_text, message):
    if any(p in answer_text for p in ("выполнено", "готово", "сделал")):
        user["score"] += 1
        user["tasks"].append(current_task)
        user["current_task"] = None
        save_users()
        await message.answer(
            f"{STATUS_EMOJIS['success']} *Поздравляю, {escape_markdown(user['name'])}!*\n\n"
            f"Ты выполнил задание! 🎉\n"
            f"⭐ Всего очков: {user['score']}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer(
            f"{STATUS_EMOJIS['info']} *Как отметить выполнение:*\n\n"
            "Напиши одно из слов:\n"
            f"{STATUS_EMOJIS['success']} выполнено\n"
            f"{STATUS_EMOJIS['success']} готово\n"
            f"{STATUS_EMOJIS['success']} сделал\n\n"
            "Или дай правильный ответ на задание!",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )

# ---------- Главная функция handle_answer ----------
async def handle_answer(message: types.Message):
    user = get_or_create_user(message.from_user)
    current_task = user.get("current_task")

    if not current_task:
        await message.answer(
            "🤔 У тебя нет активного задания.\n"
            "Используй /start чтобы получить новое!",
            reply_markup=get_main_keyboard()
        )
        return

    answer_text = message.text.lower().strip()

    if isinstance(current_task, dict):
        await handle_dict_task(user, current_task, answer_text, message)
    else:
        await handle_string_task(user, current_task, answer_text, message)

async def handle_answer(message: types.Message):
    user = get_or_create_user(message.from_user)
    current_task = user.get("current_task")

    if not current_task:
        await message.answer(
            "🤔 У тебя нет активного задания.\n"
            "Используй /start чтобы получить новое!",
            reply_markup=get_main_keyboard()
        )
        return

    answer_text = message.text.lower().strip()

    if isinstance(current_task, dict):
        await handle_dict_task(user, current_task, answer_text, message)
    else:
        await handle_string_task(user, current_task, answer_text, message)

async def handle_dict_task(user, current_task, answer_text, message):
    correct_answers = [ans.lower() for ans in current_task.get("answer", [])]
    is_correct = any(answer_text == ans or ans in answer_text for ans in correct_answers)

    if is_correct:
        await process_correct_answer(user, current_task, message)
    else:
        await process_incorrect_answer(user, current_task, message)

async def process_correct_answer(user, current_task, message):
    reward = current_task.get("reward", 5)
    old_score = user["score"]
    user["score"] += reward
    user["tasks"].append(current_task.get("id", current_task))
    user["current_task"] = None
    user["hint_index"] = 0
    save_users()

    level_up = get_level_up_msg(user["score"], old_score)
    response = compose_success_response(reward, user, current_task.get("explanation", ""), level_up)
    await message.answer(response, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def handle_string_task(user, current_task, answer_text, message):
    if any(p in answer_text for p in ("выполнено", "готово", "сделал")):
        user["score"] += 1
        user["tasks"].append(current_task)
        user["current_task"] = None
        save_users()
        await message.answer(
            f"{STATUS_EMOJIS['success']} *Поздравляю, {escape_markdown(user['name'])}!*\n\n"
            f"Ты выполнил задание! 🎉\n"
            f"⭐ Всего очков: {user['score']}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer(
            f"{STATUS_EMOJIS['info']} *Как отметить выполнение:*\n\n"
            "Напиши одно из слов:\n"
            f"{STATUS_EMOJIS['success']} выполнено\n"
            f"{STATUS_EMOJIS['success']} готово\n"
            f"{STATUS_EMOJIS['success']} сделал\n\n"
            "Или дай правильный ответ на задание!",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )


async def show_categories(callback: types.CallbackQuery):
    user = get_or_create_user(callback.from_user)
    await callback.message.edit_text(
        "📂 *Выберите категории заданий*\n"
        "Нажмите на категорию, чтобы включить/отключить её.",
        reply_markup=categories_keyboard(user.get("selected_categories", [])),
        parse_mode="Markdown"
    )
    await callback.answer()


async def categories_callback(callback: types.CallbackQuery):
    user = get_or_create_user(callback.from_user)
    data = callback.data
    if data == "cat_save":
        await callback.message.edit_text(
            "✅ Настройки категорий сохранены!",
            reply_markup=get_main_keyboard()
        )
        await callback.answer()
        return
    cat = data[4:]
    if "selected_categories" not in user:
        user["selected_categories"] = []
    if cat in user["selected_categories"]:
        user["selected_categories"].remove(cat)
    else:
        user["selected_categories"].append(cat)
    save_users()
    await callback.message.edit_reply_markup(
        reply_markup=categories_keyboard(user["selected_categories"])
    )
    await callback.answer()


async def handle_callback(callback: types.CallbackQuery):
    await callback.answer()
    if callback.data == "get_task":
        await cmd_start(callback.message)
    elif callback.data == "hint":
        await cmd_hint(callback.message)
    elif callback.data == "stats":
        await cmd_score(callback.message)
    elif callback.data == "leaderboard":
        await cmd_leaderboard(callback.message)
    elif callback.data == "daily_bonus":
        await cmd_daily_bonus(callback.message)
    elif callback.data == "help":
        await cmd_help(callback.message)
    elif callback.data == "show_categories":
        await show_categories(callback)
    elif callback.data.startswith("cat_"):
        await categories_callback(callback)


async def main():
    global users
    users = load_users()
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_score, Command("score"))
    dp.message.register(cmd_history_tasks, Command("history"))
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(cmd_leaderboard, Command("leaderboard"))
    dp.message.register(cmd_daily_bonus, Command("bonus"))
    dp.message.register(handle_answer)
    dp.callback_query.register(handle_callback)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())