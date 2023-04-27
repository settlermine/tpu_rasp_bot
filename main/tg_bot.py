import re
from telebot.async_telebot import AsyncTeleBot
import telebot
import pickle
from telebot import types
import sqlite3 as sq
import requests
from site_parser import get_day_timetable
import datetime
import pytz
import asyncio
import logging
from telebot import asyncio_helper

#This line can be deleted if it doesn't work with it
asyncio_helper.proxy = 'http://proxy.server:3128'

class CommandMessages:
    def __new__(cls): pass

    NEXT_LESSON_MESSAGE = '⬇️Следующая пара'
    CURRENT_DAY_MESSAGE = '⏺Расписание на этот день'
    NEXT_DAY_MESSAGE = '➡️Расписание на следующий день'
    CURRENT_WEEK_MESSAGE = '📅Текущая неделя'
    NEXT_WEEK_MESSAGE = '📆Следующая неделя'
    CHANGE_GROUP_MESSAGE = '⚙️Изменить группу'
    SET_GROUP_MESSAGE = '⚙️Установить группу'
    BACK_TO_MENU_MESSAGE = 'Выйти в основное меню'
    DATE_TIMETABLE_MESSAGE = '📅Расписание по дате'


LESSONS_TIME = [(datetime.time(8, 30), datetime.time(10, 5)),
                (datetime.time(10, 25), datetime.time(12, 0)),
                (datetime.time(12, 40), datetime.time(14, 15)),
                (datetime.time(14, 35), datetime.time(16, 10)),
                (datetime.time(16, 30), datetime.time(18, 5)),
                (datetime.time(18, 25), datetime.time(20, 00)),
                (datetime.time(20, 20), datetime.time(21, 55))]
#LESSONS_TIME = ['8:30 - 10:05', '10:35 - 12:00', '12:40 - 14:15', '14:35 - 16:10', '16:30 - 18:05', '18:25 - 20:00', '20:20 - 21:55']
WEEKDAY_NAMES = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
REGION = 'Asia/Tomsk'


def get_lesson_message(lessons, time, is_now=False):
    head = f'️<b><u>{str(time[0])[:5]} - {str(time[1])[:5]}</u></b>'
    if is_now:
        head = '️➡' + head + '⬅'
    head += '\n'
    lessons_strings = []
    for lesson in lessons:
        lesson_string = ''
        if lesson:
            if 'subject' in lesson:
                lesson_string += f'<b><i>{lesson["subject"]}</i></b>\n'
            if 'teacher' in lesson:
                lesson_string += f'{lesson["teacher"]}\n'
            if 'building' in lesson:
                lesson_string += f'к. {lesson["building"]}'
                if 'classroom' in lesson:
                    lesson_string += f', ауд. {lesson["classroom"]}'
                lesson_string += "\n"
        else:
            lesson_string += '<b><i>Окно</i></b>\n'
        lessons_strings.append(lesson_string)
    return head + ''.join(lessons_strings)


def get_weekend_message(timetable, date, weekday):
    return f'<b>-{WEEKDAY_NAMES[weekday]} {date}-</b>\n\n' + 'Выходной день'


def get_day_message(timetable, date, weekday):
    head = f'<b>-{WEEKDAY_NAMES[weekday]} {date}-</b>\n\n'
    lesson_strings = [get_lesson_message(x, LESSONS_TIME[i]) for i, x in enumerate(timetable)]
    return head + '\n'.join(lesson_strings)


def set_user_group_id(user_id, group_id):
    with sq.connect("users.db") as con:
        cur = con.cursor()
        cur.execute(f'''DELETE FROM tg_users WHERE user_id = {user_id}''')
        cur.execute(f'''INSERT INTO tg_users VALUES({user_id}, {group_id})''')


def get_user_group_id(user_id):
    with sq.connect("main/users.db") as con:
        cur = con.cursor()
        cur.execute(f'''SELECT group_id FROM tg_users WHERE user_id = {user_id}''')
        try:
            group_id = cur.fetchall()[0][0]
            return group_id
        except IndexError:
            return None


if __name__ == '__main__':
    users_statements = {}
    with open('main/token.bin', 'rb') as file:
        token = pickle.load(file)
    bot = AsyncTeleBot(token, parse_mode='html')
    logger = telebot.logger
    telebot.logger.setLevel(logging.DEBUG)

    def start_menu(user_id):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        if get_user_group_id(user_id):
            next_lesson = types.KeyboardButton(CommandMessages.NEXT_LESSON_MESSAGE)
            current_day = types.KeyboardButton(CommandMessages.CURRENT_DAY_MESSAGE)
            next_day = types.KeyboardButton(CommandMessages.NEXT_DAY_MESSAGE)
            date_day = types.KeyboardButton(CommandMessages.DATE_TIMETABLE_MESSAGE)
            current_week = types.KeyboardButton(CommandMessages.CURRENT_WEEK_MESSAGE)
            next_week = types.KeyboardButton(CommandMessages.NEXT_WEEK_MESSAGE)
            change_group = types.KeyboardButton(CommandMessages.SET_GROUP_MESSAGE)
            markup.add(next_lesson, current_day, next_day, date_day, current_week, next_week, change_group)
        else:
            set_group = types.KeyboardButton(CommandMessages.SET_GROUP_MESSAGE)
            markup.add(set_group)
        return markup

    @bot.message_handler(commands=['start'])
    async def start(message):
        markup = start_menu(message.chat.id)
        await bot.send_message(message.chat.id,
                               'Добро пожаловать в <b>Telegram-бота</b> для получения расписания ТПУ!',
                               reply_markup=markup)

    async def send_day_timetable(user_id: int, timetable):
        if any(timetable['timetable']):
            await bot.send_message(user_id, get_day_message(**timetable))
        else:
            await bot.send_message(user_id, get_weekend_message(**timetable))

    @bot.message_handler(content_types=['text'])
    async def handle_message(message):
        user_id = message.chat.id
        if message.chat.type != 'private':
            return

        if message.text == CommandMessages.CHANGE_GROUP_MESSAGE or message.text == CommandMessages.SET_GROUP_MESSAGE:
            users_statements[user_id] = 'changing_group'
            caption = 'Введите id своей группы. Чтобы его узнать, зайдите на сайт с расписанием и откройте расписание для своей группы на любую неделю. Цифры, подчеркнутые на скриншоте, в url страницы будут являться id вашей группы. Это нужно сделать единожды.'
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
            button = types.KeyboardButton(CommandMessages.BACK_TO_MENU_MESSAGE)
            markup.add(button)
            with open('main/group_id.png', 'rb') as photo:
                await bot.send_photo(user_id, photo, caption=caption, reply_markup=markup)

        elif message.text == CommandMessages.BACK_TO_MENU_MESSAGE:
            try:
                del users_statements[user_id]
            except KeyError:
                pass
            await start(message)

        elif message.text == CommandMessages.CURRENT_DAY_MESSAGE:
            date = datetime.datetime.now(pytz.timezone(REGION))
            timetable = get_day_timetable(get_user_group_id(user_id), date)
            await send_day_timetable(user_id, timetable)

        elif message.text == CommandMessages.NEXT_DAY_MESSAGE:
            date = datetime.datetime.now(pytz.timezone(REGION)) + datetime.timedelta(days=1)
            timetable = get_day_timetable(get_user_group_id(user_id), date)
            await send_day_timetable(user_id, timetable)

        elif message.text == CommandMessages.DATE_TIMETABLE_MESSAGE:
            users_statements[user_id] = 'choosing_date'
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
            button = types.KeyboardButton(CommandMessages.BACK_TO_MENU_MESSAGE)
            markup.add(button)
            await bot.send_message(user_id, 'Напишите дату в формате ДД.ММ.ГГ', reply_markup=markup)

        elif message.text == CommandMessages.CURRENT_WEEK_MESSAGE:
            current_date = datetime.datetime.now(pytz.timezone(REGION))
            for delta in [5 - current_date.weekday() - i for i in range(5, -1, -1)]:
                date = current_date + datetime.timedelta(days=delta)
                timetable = get_day_timetable(get_user_group_id(user_id), date)
                await send_day_timetable(user_id, timetable)

        elif message.text == CommandMessages.NEXT_WEEK_MESSAGE:
            current_date = datetime.datetime.now(pytz.timezone(REGION)) + datetime.timedelta(days=7)
            for delta in [5 - current_date.weekday() - i for i in range(5, -1, -1)]:
                date = current_date + datetime.timedelta(days=delta)
                timetable = get_day_timetable(get_user_group_id(user_id), date)
                await send_day_timetable(user_id, timetable)

        elif message.text == CommandMessages.NEXT_LESSON_MESSAGE:
            current_datetime = datetime.datetime.now(pytz.timezone(REGION))

        else:
            if user_id not in users_statements:
                return
            if users_statements[user_id] == 'changing_group':
                r = requests.get(f'https://rasp.tpu.ru/gruppa_{message.text}/2021/40/view.html')
                if r.status_code == 404:
                    await bot.send_message(user_id, 'Некорректно введен id группы. Попробуйте еще раз.')
                else:
                    set_user_group_id(user_id, int(message.text))
                    del users_statements[user_id]
                    await bot.send_message(user_id,
                                            'Группа задана успешно!',
                                            reply_markup=start_menu(user_id))

            elif users_statements[user_id] == 'choosing_date':
                if match := re.fullmatch(r'(\d{1,2})[.](\d{1,2})[.](\d{2})', message.text):
                    day, month, year = map(int, match.groups())
                    year = 2000 + year
                    try:
                        date = datetime.date(year, month, day)
                    except ValueError:
                        await bot.send_message(user_id, 'Неправильно введена дата. Попробуйте еще раз')
                        return
                    timetable = get_day_timetable(get_user_group_id(user_id), date)
                    await send_day_timetable(user_id, timetable)
                else:
                    await bot.send_message(user_id, 'Неправильно введена дата. Попробуйте еще раз')

    asyncio.run(bot.polling(non_stop=True))
