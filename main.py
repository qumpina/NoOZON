import sqlite3
from datetime import datetime,timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
from aiogram.utils.keyboard import InlineKeyboardBuilder
import matplotlib.pyplot as plt
import io
import matplotlib.dates as mdates
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Получаем токен из .env файла
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

# Инициализация БД
def init_db():
    with sqlite3.connect('workout.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            exercise TEXT,
            weight INTEGER,
            date TEXT
        )
        ''')
        conn.commit()


init_db()

# Хранилище временных данных (exercise: user_id)
user_state = {}


# Главная клавиатура
def get_main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Помощь")],
            [types.KeyboardButton(text="Добавить запись")],
            # [types.KeyboardButton(text="Bench"), types.KeyboardButton(text="Squat"), types.KeyboardButton(text="Deadlift")],
            [types.KeyboardButton(text="Все записи"), types.KeyboardButton(text="Мои рекорды")],

        ],
        resize_keyboard=True
    )

def get_exercise_kb(with_back=True):
    buttons = [
        [types.KeyboardButton(text="Bench"), types.KeyboardButton(text="Squat"), types.KeyboardButton(text="Deadlift")]
    ]
    if with_back:
        buttons.append([types.KeyboardButton(text="Назад")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_back_kb():
    return ReplyKeyboardMarkup(keyboard=[[types.KeyboardButton(text="Назад")]], resize_keyboard=True)

# Обработчик кнопки "Назад"
@dp.message(F.text == "Назад")
async def cmd_back(message: types.Message):
    user_id = message.from_user.id
    if user_id in user_state:
        del user_state[user_id]
    await cmd_help(message)

# Команда помощи
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🏋️ Добро пожаловать в GymProgressBot!\n\n"
        "Я помогу отслеживать ваши силовые показатели в базовых упражнениях.\n\n"
        "Для справки используйте /help\n\n"
        "Выберите упражнение или действие:",
        reply_markup=get_main_kb()
    )

@dp.message(F.text == "Помощь")
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = """
    <b>🏋️ GymProgressBot - помощь по командам</b>

    <b>Основные команды:</b>
    /add - добавить запись 
    /start - главное меню
    /progress - просмотр прогресса с выбором периода
    /help - эта справка

    <b>Аналитика:</b>
    Все записи - полная история тренировок
    Мои рекорды - максимальные результаты
    /delete - удалить запись
    /clear_all - очистить всю историю

    <b>Навигация:</b>
    В любой момент можно нажать "Назад" для возврата в меню
    """
    await message.answer(help_text, parse_mode="HTML", reply_markup=get_main_kb())

# Обработка выбора упражнения
# @dp.message(F.text.in_(["Bench", "Squat", "Deadlift"]))
# async def select_exercise(message: types.Message):
#     user_state[message.from_user.id] = message.text
#     await message.answer(
#         f"Вы выбрали {message.text}. Теперь введите вес в кг:",
#         reply_markup=types.ReplyKeyboardRemove()
#     )


@dp.message(Command("progress"))
async def cmd_progress(message: types.Message):
    """Обработчик команды /progress с выбором интервала"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 месяц", callback_data="progress_1m")],
        [InlineKeyboardButton(text="6 месяцев", callback_data="progress_6m")],
        [InlineKeyboardButton(text="Все время", callback_data="progress_all")],
        [InlineKeyboardButton(text="Назад", callback_data="progress_back")]
    ])
    await message.answer(
        "📊 Выберите период для отображения прогресса:",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "progress_back")
async def progress_back(callback: types.CallbackQuery):
    await callback.message.delete()
    await cmd_help(callback.message)
    await callback.answer()


@dp.callback_query(F.data.startswith("progress_"))
async def show_progress_chart(callback: types.CallbackQuery):
    try:
        period = callback.data.split("_")[1]

        # Определяем период для фильтрации
        if period == "1m":
            date_filter = datetime.now() - timedelta(days=30)
            period_name = "1 месяц"
        elif period == "6m":
            date_filter = datetime.now() - timedelta(days=180)
            period_name = "6 месяцев"
        else:  # all
            date_filter = None
            period_name = "все время"

        # Получаем данные из БД
        with sqlite3.connect('workout.db') as conn:
            cursor = conn.cursor()

            if date_filter:
                cursor.execute('''
                SELECT exercise, date, weight FROM records 
                WHERE user_id = ? AND date >= ?
                ORDER BY date
                ''', (callback.from_user.id, date_filter.strftime("%Y-%m-%d")))
            else:
                cursor.execute('''
                SELECT exercise, date, weight FROM records 
                WHERE user_id = ?
                ORDER BY date
                ''', (callback.from_user.id,))

            records = cursor.fetchall()

        if not records:
            await callback.message.edit_text("Нет данных за выбранный период")
            return

        # Обрабатываем данные
        exercises = {}
        dates = []
        for ex, date_str, weight in records:
            date = datetime.strptime(date_str, "%Y-%m-%d").date()
            dates.append(date)

            if ex not in exercises:
                exercises[ex] = {'dates': [], 'weights': []}
            exercises[ex]['dates'].append(date)
            exercises[ex]['weights'].append(weight)

        first_date = min(dates)
        last_date = max(dates)
        total_days = (last_date - first_date).days

        # Определяем интервал для оси дат
        if total_days <= 30:
            days_interval = 7
        elif total_days <= 180:
            days_interval = 14
        else:
            days_interval = 30

        # Создаем график
        plt.style.use('seaborn-v0_8')
        plt.figure(figsize=(12, 7))

        # Рисуем графики
        for ex, data in exercises.items():
            plt.plot(data['dates'], data['weights'], 'o-', linewidth=2.5, markersize=9, label=ex)

        # Настраиваем ось дат
        ax = plt.gca()
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=days_interval))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.xticks(rotation=45, ha='right')

        # Настраиваем внешний вид
        plt.title(f"Прогресс за {period_name}\n({first_date.strftime('%d.%m.%Y')} - {last_date.strftime('%d.%m.%Y')})",
                  fontsize=14, pad=20)
        plt.xlabel("Дата", fontsize=12)
        plt.ylabel("Вес (кг)", fontsize=12)
        plt.legend(prop={'size': 10}, bbox_to_anchor=(1.02, 1), loc='upper left')
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.tight_layout()

        # Сохраняем и отправляем график
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)

        await callback.message.delete()  # Удаляем сообщение с кнопками
        await callback.message.answer_photo(
            types.BufferedInputFile(buf.getvalue(), filename="progress.png"),
            caption=f"📊 Прогресс за {period_name} ({len(records)} записей)"
        )

        plt.close()
        buf.close()

    except Exception as e:
        await callback.message.answer(f"⚠️ Ошибка: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        await callback.answer()


@dp.message(F.text == "Добавить запись")
@dp.message(Command("add"))
async def cmd_add(message: types.Message):
    """Обработчик команды добавления записи"""
    # Инициализируем состояние для пользователя
    user_state[message.from_user.id] = {
        'step': 'select_date',
        'exercise': None,
        'weight': None,
        'date': None
    }

    # Клавиатура для выбора даты
    kb = [
        [types.KeyboardButton(text="Сегодня")],
        [types.KeyboardButton(text="Ввести другую дату")],
        [types.KeyboardButton(text="Назад")]
    ]
    date_kb = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

    await message.answer(
        "📅 Выберите дату тренировки:",
        reply_markup=date_kb
    )


@dp.message(F.text == "Сегодня")
async def process_today_date(message: types.Message):
    """Обработка выбора сегодняшней даты"""
    user_id = message.from_user.id
    if user_id not in user_state or user_state[user_id]['step'] != 'select_date':
        await message.answer("Пожалуйста, начните с команды /add", reply_markup=get_main_kb())
        return

    # Сохраняем сегодняшнюю дату
    user_state[user_id]['date'] = datetime.now().strftime("%Y-%m-%d")
    user_state[user_id]['step'] = 'select_exercise'

    await message.answer(
        f"✅ Дата: {datetime.now().strftime('%d.%m.%Y')}. Теперь выберите упражнение:",
        reply_markup=get_exercise_kb()
    )


@dp.message(F.text == "Ввести другую дату")
async def process_custom_date_choice(message: types.Message):
    """Обработка выбора ввода своей даты"""
    user_id = message.from_user.id
    if user_id not in user_state or user_state[user_id]['step'] != 'select_date':
        await message.answer("Пожалуйста, начните с команды /add", reply_markup=get_main_kb())
        return

    user_state[user_id]['step'] = 'enter_custom_date'
    await message.answer(
        "📅 Введите дату в формате ДД.ММ.ГГГГ (например, 15.05.2023):",
        reply_markup=get_back_kb()
    )


@dp.message(F.text.regexp(r'^\d{2}\.\d{2}\.\d{4}$'))
async def process_custom_date(message: types.Message):
    """Обработка введённой даты"""
    user_id = message.from_user.id
    if user_id not in user_state or user_state[user_id]['step'] != 'enter_custom_date':
        await message.answer("Пожалуйста, начните с команды /add", reply_markup=get_main_kb())
        return

    try:
        # Проверяем и сохраняем дату
        date_obj = datetime.strptime(message.text, "%d.%m.%Y").date()
        today = datetime.now().date()

        if date_obj > today:
            await message.answer("Дата не может быть в будущем. Введите корректную дату:", reply_markup=get_back_kb())
            return

        user_state[user_id]['date'] = date_obj.strftime("%Y-%m-%d")
        user_state[user_id]['step'] = 'select_exercise'

        await message.answer(
            f"✅ Дата {message.text} сохранена. Теперь выберите упражнение:",
            reply_markup=get_exercise_kb()
        )

    except ValueError:
        await message.answer("Некорректный формат даты. Введите дату в формате ДД.ММ.ГГГГ:", reply_markup=get_back_kb())


@dp.message(F.text.in_(["Bench", "Squat", "Deadlift"]))
async def select_exercise(message: types.Message):
    """Обработка выбора упражнения"""
    user_id = message.from_user.id
    if user_id not in user_state or user_state[user_id]['step'] != 'select_exercise':
        await message.answer("Пожалуйста, начните с команды /add", reply_markup=get_main_kb())
        return

    # Сохраняем упражнение
    user_state[user_id]['exercise'] = message.text
    user_state[user_id]['step'] = 'enter_weight'

    await message.answer(
        f"Вы выбрали {message.text}. Теперь введите вес в кг:",
        reply_markup=get_back_kb()
    )


@dp.message(F.text.isdigit())
async def handle_weight_input(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_state:
        await message.answer("Сначала выберите упражнение!", reply_markup=get_main_kb())
        return

    state = user_state[user_id]

    # Изменено: проверяем step вместо mode
    if state.get('step') == 'enter_weight':
        try:
            weight = int(message.text)
            if not 1 <= weight <= 1000:
                raise ValueError

            exercise = state['exercise']
            date = state['date']

            with sqlite3.connect('workout.db') as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO records (user_id, exercise, weight, date) VALUES (?, ?, ?, ?)",
                    (user_id, exercise, weight, date)
                )
                conn.commit()

            display_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d.%m.%Y")
            await message.answer(
                f"✅ {exercise}: {weight} кг за {display_date} сохранён!",
                reply_markup=get_main_kb()
            )

            del user_state[user_id]  # Очищаем состояние

        except ValueError:
            await message.answer("Введите корректный вес (1-1000 кг)", reply_markup=get_back_kb())
        except Exception as e:
            await message.answer(f"⚠️ Ошибка при сохранении: {str(e)}", reply_markup=get_main_kb())
            if user_id in user_state:
                del user_state[user_id]
    else:
        await message.answer("Неверный контекст для ввода веса", reply_markup=get_main_kb())


@dp.message(F.text == "Все записи")
@dp.message(Command("all_records"))
async def show_all_records(message: types.Message):
    with sqlite3.connect('workout.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT exercise, weight, date FROM records 
        WHERE user_id = ?
        ORDER BY date DESC, exercise
        ''', (message.from_user.id,))

        records = cursor.fetchall()

        if not records:
            await message.answer("У вас пока нет записей")
            return

        response = "📋 Все ваши записи:\n\n"
        for ex, weight, date in records:
            response += f"{ex}: {weight} кг ({date})\n"

        # Разбиваем на части если слишком длинное сообщение
        if len(response) > 4000:
            parts = [response[i:i + 4000] for i in range(0, len(response), 4000)]
            for part in parts:
                await message.answer(part)
        else:
            await message.answer(response)


# Показать рекорды (переработанная stats)
@dp.message(F.text == "Мои рекорды")
@dp.message(Command("records"))
async def show_records(message: types.Message):
    with sqlite3.connect('workout.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT exercise, MAX(weight), date FROM (
            SELECT exercise, weight, MAX(date) as date 
            FROM records 
            WHERE user_id = ?
            GROUP BY exercise, weight
        ) GROUP BY exercise
        ''', (message.from_user.id,))

        records = cursor.fetchall()

        if not records:
            await message.answer("У вас пока нет рекордов")
            return

        response = "🏆 Ваши рекорды:\n\n"
        for ex, weight, date in records:
            response += f"{ex}: {weight} кг (дата: {date})\n"

        await message.answer(response)


# Удаление записей
@dp.message(Command("delete"))
async def delete_records_menu(message: types.Message):
    with sqlite3.connect('workout.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT id, exercise, weight, date FROM records 
        WHERE user_id = ?
        ORDER BY date DESC
        LIMIT 10
        ''', (message.from_user.id,))

        records = cursor.fetchall()

    if not records:
        await message.answer("У вас нет записей для удаления")
        return

    builder = InlineKeyboardBuilder()
    for record in records:
        record_id, exercise, weight, date = record
        builder.button(
            text=f"{exercise} {weight}кг ({date})",
            callback_data=f"delete_{record_id}"
        )
    builder.adjust(1)

    await message.answer(
        "Выберите запись для удаления:",
        reply_markup=builder.as_markup()
    )


@dp.callback_query(F.data.startswith("delete_"))
async def delete_record(callback: types.CallbackQuery):
    record_id = int(callback.data.split("_")[1])

    with sqlite3.connect('workout.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT exercise, weight, date FROM records WHERE id = ?', (record_id,))
        record = cursor.fetchone()

        if record:
            exercise, weight, date = record
            cursor.execute('DELETE FROM records WHERE id = ?', (record_id,))
            conn.commit()
            await callback.message.edit_text(
                f"✅ Удалено: {exercise} {weight} кг ({date})",
                reply_markup=None
            )
        else:
            await callback.answer("Запись уже удалена")

    await callback.answer()


@dp.message(Command("clear_all"))
async def clear_all_records(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="Да, удалить всё", callback_data="confirm_clear")
    builder.button(text="Отмена", callback_data="cancel_clear")

    await message.answer(
        "⚠️ Вы уверены, что хотите удалить ВСЕ свои записи?",
        reply_markup=builder.as_markup()
    )


@dp.callback_query(F.data == "confirm_clear")
async def confirm_clear(callback: types.CallbackQuery):
    with sqlite3.connect('workout.db') as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM records WHERE user_id = ?', (callback.from_user.id,))
        conn.commit()

    await callback.message.edit_text("Все ваши записи удалены", reply_markup=None)
    await callback.answer()


@dp.callback_query(F.data == "cancel_clear")
async def cancel_clear(callback: types.CallbackQuery):
    await callback.message.edit_text("Отменено", reply_markup=None)
    await callback.answer()


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())