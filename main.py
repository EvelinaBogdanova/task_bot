import asyncio
import random
import json
import secrets
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Эмодзи для категорий, сложностей, статусов
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

users = {}


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


def get_today_task():
    if not TASKS:
        return None
    day = datetime.now().day
    return TASKS[(day - 1) % len(TASKS)]


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
    name = user.get("name", "Пользователь")
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
    if score < 50:
        next_level = 50
        progress = int((score / next_level) * 20)
        bar = "█" * progress + "░" * (20 - progress)
        text += "\n📈 *Прогресс до следующего уровня:*\n"
        text += f"`{bar}` {score}/{next_level}\n"
    return text


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
            InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")
        ]
    ])
    return keyboard


async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user = users.get(user_id)
    if not user:
        user = {
            "id": user_id,
            "name": message.from_user.username if message.from_user.username else f"user_{user_id}",
            "score": 0,
            "tasks": [],
            "current_task": None,
            "last_bonus": None
        }
        users[user_id] = user
        await message.answer(
            f"🎉 *Добро пожаловать в TaskBot!*\n\n"
            f"👋 Привет, {user['name']}!\n"
            f"Я помогу тебе развиваться с помощью ежедневных заданий.\n\n"
            f"🔹 Выполняй задания, получай очки и повышай уровень!\n"
            f"🔹 Используй кнопки ниже для навигации.",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    today_task = get_today_task()
    if today_task:
        user["current_task"] = today_task
        await message.answer(
            f"{STATUS_EMOJIS['info']} *Твое задание на сегодня:*\n\n"
            f"{format_task(today_task)}",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "Сегодня для тебя нет задания. Проверьте taskbot.txt!",
            reply_markup=get_main_keyboard()
        )


async def cmd_score(message: types.Message):
    user_id = message.from_user.id
    user = users.get(user_id)
    if not user:
        await message.answer(
            "❌ Вы не зарегистрированы.\n"
            "Используйте /start для начала!",
            reply_markup=get_main_keyboard()
        )
        return
    await message.answer(
        format_user_stats(user),
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )


async def cmd_leaderboard(message: types.Message):
    if not users:
        await message.answer("😕 Пока нет пользователей в рейтинге!")
        return
    sorted_users = sorted(users.values(), key=lambda x: x["score"], reverse=True)[:10]
    text = f"{STATUS_EMOJIS['trophy']} *Топ пользователей*\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, user in enumerate(sorted_users, 1):
        medal = medals[i - 1] if i <= 3 else f"{i}."
        name = user.get("name", "Аноним")
        score = user.get("score", 0)
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
        user_score = users[user_id]["score"]
        position = sum(1 for u in users.values() if u["score"] > user_score) + 1
        text += f"\n📊 *Твоя позиция:* {position} место"
        text += f"\n⭐ *Твои очки:* {user_score}"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard())


async def cmd_hint(message: types.Message):
    user_id = message.from_user.id
    user = users.get(user_id)
    if not user or not user.get("current_task"):
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
    user_id = message.from_user.id
    user = users.get(user_id)
    if not user:
        await message.answer("❌ Используйте /start для регистрации!")
        return
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
    if user["score"] >= 50 and user["score"] - bonus < 50:
        level_msg = "\n\n🎉 *Поздравляю! Ты достиг уровня* 🔍 *Исследователь!*"
    elif user["score"] >= 100 and user["score"] - bonus < 100:
        level_msg = "\n\n🎉 *Поздравляю! Ты достиг уровня* ⭐ *Мастер!*"
    elif user["score"] >= 200 and user["score"] - bonus < 200:
        level_msg = "\n\n👑 *Поздравляю! Ты достиг уровня* 👑 *Легенда!*"
    else:
        level_msg = ""
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
/help — ℹ️ Показать эту справку

*Кнопки быстрого доступа:*
📝 Задание дня — Получить новое задание
💡 Подсказка — Получить подсказку к заданию
📊 Статистика — Посмотреть свой прогресс
🏆 Рейтинг — Топ пользователей
🎁 Бонус — Получить ежедневный бонус

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


async def handle_answer(message: types.Message):
    user_id = message.from_user.id
    user = users.get(user_id)
    if not user:
        await message.answer(
            "❌ Вы не зарегистрированы.\n"
            "Используйте /start для начала!",
            reply_markup=get_main_keyboard()
        )
        return

    current_task = user.get("current_task")
    if not current_task:
        await message.answer(
            "🤔 У тебя нет активного задания.\n"
            "Используй /start чтобы получить новое!",
            reply_markup=get_main_keyboard()
        )
        return

    answer_text = message.text.lower().strip()
    
    if isinstance(current_task, dict) and "answer" in current_task:
        correct_answers = [ans.lower() for ans in current_task["answer"]]
        
        if any(answer_text == ans or ans in answer_text for ans in correct_answers):
            reward = current_task.get("reward", 5)
            old_score = user["score"]  # Сохраняем старый счет
            user["score"] += reward
            user["tasks"].append(current_task.get("id", current_task))
            user["current_task"] = None
            user["hint_index"] = 0
            level_up = ""
            if user["score"] >= 200 and old_score < 200:
                level_up = "\n\n👑 *НОВЫЙ УРОВЕНЬ: ЛЕГЕНДА!* 👑"
            elif user["score"] >= 100 and old_score < 100:
                level_up = "\n\n⭐ *НОВЫЙ УРОВЕНЬ: МАСТЕР!* ⭐"
            elif user["score"] >= 50 and old_score < 50:
                level_up = "\n\n🔍 *НОВЫЙ УРОВЕНЬ: ИССЛЕДОВАТЕЛЬ!* 🔍"
            explanation = current_task.get("explanation", "")
            response = f"{STATUS_EMOJIS['success']} *Отлично! Правильный ответ!*\n\n"
            response += f"➕ +{reward} очков\n"
            response += f"⭐ Всего очков: {user['score']}\n"
            if explanation:
                response += f"\n📖 *Объяснение:* {explanation}\n"
            response += level_up
            
            await message.answer(response, parse_mode="Markdown", reply_markup=get_main_keyboard())
        else:
            hints = current_task.get("hints", [])
            used_hints = user.get("hint_index", 0)
            remaining_hints = len(hints) - used_hints
            
            if remaining_hints <= 0 and hints:
                response = f"{STATUS_EMOJIS['warning']} *Неправильно!*\n\n"
                response += "💡 Вот правильный ответ:\n"
                response += f"`{current_task['answer'][0]}`\n\n"
                response += "Попробуй следующее задание через /start"
                user["current_task"] = None
                user["hint_index"] = 0
            else:
                response = f"{STATUS_EMOJIS['error']} *Неправильно!*\n\n"
                if remaining_hints > 0:
                    response += f"💡 Осталось подсказок: {remaining_hints}\n"
                    response += "Используй кнопку '💡 Подсказка'"
                else:
                    response += "💡 Подсказки закончились!\n"
                    response += "Попробуй еще раз или используй /start для нового задания"
            
            await message.answer(response, parse_mode="Markdown", reply_markup=get_main_keyboard())
    else:
        if "выполнено" in answer_text or "готово" in answer_text or "сделал" in answer_text:
            user["score"] += 1
            user["tasks"].append(current_task)
            user["current_task"] = None
            
            await message.answer(
                f"{STATUS_EMOJIS['success']} *Поздравляю, {user['name']}!*\n\n"
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

            async def cmd_history_tasks():
                user_id = message.from_user.id
                history = [task for task in user_stats[user_id] if tasks['date'] >= datetime.now()]

                if not history:
                    await message.answer('there ara no tasks')
                    return

                text = "the history of completed tasks: n/ n/"


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


async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_score, Command("score"))
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(cmd_leaderboard, Command("leaderboard"))
    dp.message.register(cmd_daily_bonus, Command("bonus"))
    dp.message.register(handle_answer)
    dp.callback_query.register(handle_callback)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())