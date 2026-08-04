import os
import logging
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("Переменная TELEGRAM_BOT_TOKEN не установлена!")

logging.basicConfig(level=logging.INFO)

def init_db():
    conn = sqlite3.connect('fitness_bot.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            subscribe_start DATE,
            day_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            promo_used INTEGER DEFAULT 0,
            last_training_date DATE
        )
    ''')
    cur.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cur.fetchall()]
    if 'promo_used' not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN promo_used INTEGER DEFAULT 0")
    if 'last_training_date' not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN last_training_date DATE")
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('fitness_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cur.fetchone()
    conn.close()
    return user

def add_user(user_id):
    conn = sqlite3.connect('fitness_bot.db')
    cur = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    cur.execute("INSERT OR IGNORE INTO users (user_id, subscribe_start, last_training_date) VALUES (?, ?, ?)", 
                (user_id, today, None))
    conn.commit()
    conn.close()

def update_day_count(user_id, new_day):
    conn = sqlite3.connect('fitness_bot.db')
    cur = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    cur.execute("UPDATE users SET day_count = ?, last_training_date = ? WHERE user_id = ?", 
                (new_day, today, user_id))
    conn.commit()
    conn.close()

def activate_promo(user_id):
    conn = sqlite3.connect('fitness_bot.db')
    cur = conn.cursor()
    cur.execute("UPDATE users SET promo_used = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def has_access(user_id):
    user = get_user(user_id)
    return user is not None and user[4] == 1

# ====================================================
#   НОВЫЕ ТЕКСТЫ ТРЕНИРОВОК (по вашему списку)
# ====================================================
TEXTS = {
    "1": "🔄 День 1: Круговая 30 мин",
    "2": "🔄 День 2: Круговая 35 мин",
    "3": "🎯 День 3: 8 по 50",
    "4": "🧘 День 4: ОТДЫХ",
    "5": "💪 День 5: Блоковая 30 мин",
    "6": "🔄 День 6: Круговая 30 мин",
    "7": "💪 День 7: Блоковая 30 мин",
    "8": "🧘 День 8: ОТДЫХ",
    "9": "🔺 День 9: Пирамида 20 мин",
    "10": "💪 День 10: Блоковая 35 мин",
    "11": "🔺 День 11: Пирамида 25 мин",
    "12": "🧘 День 12: ОТДЫХ",
    "13": "🔺 День 13: Пирамида 20 мин",
    "14": "💪 День 14: Блоковая 35 мин",
    "15": "🔺 День 15: Пирамида 30 мин",
    "16": "🧘 День 16: ОТДЫХ",
    "17": "💪 День 17: Блоковая 30 мин",
    "18": "💪 День 18: Блоковая 35 мин",
    "19": "💪 День 19: Блоковая 40 мин",
    "20": "🧘 День 20: ОТДЫХ",
    "21": "🎯 День 21: 8 по 50 + Результаты"
}

# ====================================================
#   ГИФКИ (пока только для ДНЯ 1)
# ====================================================
# Укажите количество гифок для каждого дня.
# Для дней без гифок ставьте 0 или просто не указывайте.
GIFS_PER_DAY = {
    1: 8,   # Например, 3 упражнения в круговой тренировке дня 1
    # 2: 0,
    # 3: 0,
    # ... остальные дни пока без гифок
}

# БАЗОВЫЙ URL ДЛЯ ГИФОК (ЗАМЕНИТЕ НА СВОЙ!)
# Пример: https://raw.githubusercontent.com/ваш_логин/fitness-bot/main/
GIF_BASE_URL = "https://raw.githubusercontent.com/egorushka681/fitness-bot/main/"

def get_training_data(day_number):
    text = TEXTS.get(str(day_number), "📅 День отдыха или итогов.")
    count = GIFS_PER_DAY.get(day_number, 0)
    gifs = []
    for i in range(1, count + 1):
        gifs.append(f"{GIF_BASE_URL}day{day_number}_{i}.gif")
    return {"text": text, "gifs": gifs}

# ====================================================
#   ПРОМОКОДЫ (обновлены)
# ====================================================
VALID_PROMOS = ["SHUSHA2301", "START681"]

# ====================================================
#   КОМАНДЫ БОТА
# ====================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    add_user(user_id)
    keyboard = [["🏋️ Тренировка сегодня"], ["🎁 Ввести промокод"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "👋 Привет! Я твой фитнес-тренер.\n"
        "Чтобы получить доступ к тренировкам, введи промокод.\n"
        "Нажми кнопку «Ввести промокод» или отправь /promo.",
        reply_markup=reply_markup
    )

async def promo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✏️ Введите промокод:")

async def handle_promo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    promo = update.message.text.strip()
    if promo in VALID_PROMOS:
        activate_promo(user_id)
        await update.message.reply_text("✅ Промокод активирован! Теперь вам доступны тренировки.")
    else:
        await update.message.reply_text("❌ Неверный промокод. Попробуйте ещё раз.")

async def today_training(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not has_access(user_id):
        await update.message.reply_text("⛔ Доступ запрещён. Введите промокод через /promo.")
        return
    user = get_user(user_id)
    day = user[2] + 1
    if day > 21:
        keyboard = [[InlineKeyboardButton("✅ Начать новый цикл", callback_data='renew')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🎉 Вы завершили 21-дневный план!\nХотите пройти его заново? Нажмите кнопку.",
            reply_markup=reply_markup
        )
        return
    data = get_training_data(day)
    text = f"📅 Тренировка дня {day}:\n{data['text']}"
    await update.message.reply_text(text)
    # Отправляем гифки, если они есть
    for idx, url in enumerate(data['gifs'], start=1):
        try:
            await update.message.send_document(documentn=url, caption=f"Упражнение {idx}")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка {e}")

async def renew_cycle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    conn = sqlite3.connect('fitness_bot.db')
    cur = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    cur.execute("UPDATE users SET subscribe_start = ?, day_count = 0, last_training_date = ? WHERE user_id = ?", 
                (today, None, user_id))
    conn.commit()
    conn.close()
    await query.edit_message_text("✅ Новый цикл начался! Завтра первая тренировка.")

async def scheduled_job(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('fitness_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT user_id, day_count FROM users WHERE promo_used = 1 AND is_active = 1")
    users = cur.fetchall()
    conn.close()
    for user_id, day_count in users:
        day = day_count + 1
        if day <= 21:
            data = get_training_data(day)
            text = f"🏋️ Тренировка дня {day}:\n{data['text']}"
            try:
                await context.bot.send_message(chat_id=user_id, text=text)
                for idx, url in enumerate(data['gifs'], start=1):
                    await context.bot.send_animation(chat_id=user_id, animation=url, caption=f"Упражнение {idx}")
                update_day_count(user_id, day)
            except Exception as e:
                logging.error(f"Ошибка отправки {user_id}: {e}")
        else:
            keyboard = [[InlineKeyboardButton("✅ Начать новый цикл", callback_data='renew')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="🎉 Вы завершили 21-дневный план! Хотите начать заново?",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logging.error(f"Ошибка финала {user_id}: {e}")

def start_scheduler(application):
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: scheduled_job(application), 'cron', hour=9, minute=0)
    scheduler.start()

def main():
    init_db()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("promo", promo_command))
    application.add_handler(CommandHandler("today", today_training))
    application.add_handler(MessageHandler(filters.Text("🏋️ Тренировка сегодня"), today_training))
    application.add_handler(MessageHandler(filters.Text("🎁 Ввести промокод"), promo_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_promo_input))
    application.add_handler(CallbackQueryHandler(renew_cycle, pattern="renew"))
    start_scheduler(application)
    print("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()
