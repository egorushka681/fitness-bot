import os
import logging
import sqlite3
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler

# ========== 1. НАСТРОЙКА ==========
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # Токен будет взят из переменных окружения на сервере
if not TOKEN:
    raise ValueError("Переменная TELEGRAM_BOT_TOKEN не установлена!")

logging.basicConfig(level=logging.INFO)

# ========== 2. БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('fitness_bot.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            subscribe_start DATE,
            day_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            promo_used INTEGER DEFAULT 0
        )
    ''')
    cur.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cur.fetchall()]
    if 'promo_used' not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN promo_used INTEGER DEFAULT 0")
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
    cur.execute("INSERT OR IGNORE INTO users (user_id, subscribe_start) VALUES (?, ?)", (user_id, today))
    conn.commit()
    conn.close()

def update_day_count(user_id):
    conn = sqlite3.connect('fitness_bot.db')
    cur = conn.cursor()
    cur.execute("UPDATE users SET day_count = day_count + 1 WHERE user_id = ?", (user_id,))
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

# ========== 3. ДАННЫЕ ТРЕНИРОВОК (тексты + гифки) ==========
# --- 3.1 Загружаем тексты из JSON-файла (будет создан позже) ---
def load_texts():
    try:
        with open('texts.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # Если файла нет, создаём заглушку
        default = {str(i): f"🏋️ Тренировка дня {i}" for i in range(1, 22)}
        with open('texts.json', 'w', encoding='utf-8') as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
        return default

TEXTS = load_texts()

# --- 3.2 Количество гифок по дням (укажите ваши цифры) ---
# GIFS_PER_DAY = {
#    1: 8, 2: 8, 3: 8, 4: 0, 5: 12, 6: 8, 7: 12, 8: 0,
#    9: 6 , 10: 12, 11: 7, 12: 0, 13: 6, 14: 12, 15: 7, 16: 0, 17: 12, 18: 12, 19: 12, 20: 0, 21: 8 
}

# --- 3.3 Базовый URL для гифок (ЗАМЕНИТЕ НА СВОЙ!) ---
# Это ссылка на ваш репозиторий на GitHub, где лежат гифки.
# ВАЖНО: замените "ВАШ_ЛОГИН" и "НАЗВАНИЕ_РЕПОЗИТОРИЯ" на свои.
GIF_BASE_URL = "https://raw.githubusercontent.com/ВАШ_ЛОГИН/НАЗВАНИЕ_РЕПОЗИТОРИЯ/main/"

def get_training_data(day_number):
    text = TEXTS.get(str(day_number), "📅 День отдыха.")
   # count = GIFS_PER_DAY.get(day_number, 0)
   # gifs = []
    # for i in range(1, count + 1):
       # gifs.append(f"{GIF_BASE_URL}day{day_number}_{i}.gif")
    return {"text": text, "gifs": []}

# ========== 4. ВАЛИДНЫЕ ПРОМОКОДЫ ==========
VALID_PROMOS = ["SHUSHA2301", "START681"]  # Добавьте свои

# ========== 5. КОМАНДЫ БОТА ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    add_user(user_id)
    keyboard = [
        ["🏋️ Тренировка сегодня"],
        ["🎁 Ввести промокод"]
    ]
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
            "🎉 Вы завершили 21-дневный план!\n"
            "Хотите пройти его заново? Нажмите кнопку.",
            reply_markup=reply_markup
        )
        return
    data = get_training_data(day)
    text = f"📅 Тренировка дня {day}:\n{data['text']}"
   # gifs = data['gifs']
    await update.message.reply_text(text)
   # for idx, url in enumerate(gifs, start=1):
        # try:
       #     await update.message.reply_animation(animation=url, caption=f"Упражнение {idx}")
      #  except Exception as e:
        #   await update.message.reply_text(f"❌ Не удалось загрузить упражнение {idx}: {e}")
    update_day_count(user_id)

async def renew_cycle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    conn = sqlite3.connect('fitness_bot.db')
    cur = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    cur.execute("UPDATE users SET subscribe_start = ?, day_count = 0 WHERE user_id = ?", (today, user_id))
    conn.commit()
    conn.close()
    await query.edit_message_text("✅ Новый цикл начался! Завтра первая тренировка.")

# ========== 6. ЕЖЕДНЕВНАЯ РАССЫЛКА ==========
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
           # gifs = data['gifs']
            try:
                await context.bot.send_message(chat_id=user_id, text=text)
               # for idx, url in enumerate(gifs, start=1):
               #     await context.bot.send_animation(chat_id=user_id, animation=url, caption=f"Упражнение {idx}")
                conn = sqlite3.connect('fitness_bot.db')
                cur = conn.cursor()
                cur.execute("UPDATE users SET day_count = ? WHERE user_id = ?", (day, user_id))
                conn.commit()
                conn.close()
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

# ========== 7. ЗАПУСК ==========
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
