import datetime
from collections import defaultdict
import sqlite3
import io
import telebot
import requests
from PIL import Image
import os

token = os.getenv('TOKEN')
tb = telebot.TeleBot(token)

class SQLighter:
    def __init__(self, database):
        """Подключаемся к БД и сохраняем курсор соединения"""
        self.connection = sqlite3.connect(database, check_same_thread=False)
        self.cursor = self.connection.cursor()
        self.cursor.execute("CREATE TABLE IF NOT EXISTS subscribers (user_id VARCHAR(30), date_rec DATETIME, photo BLOB, place VARCHAR(150), lat VARCHAR(30), lon VARCHAR(30))")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS subs_id (user_id VARCHAR(30), f_name VARCHAR(40), l_name VARCHAR(40), date_rec DATETIME)")
        
    def add_subscriber(self, message):
        """Добавляем нового пользователя"""
        user_id = message.chat.id
        f = message.chat.first_name
        l = message.chat.last_name
        dt = datetime.datetime.now()
        with self.connection:
            return self.cursor.execute("INSERT INTO subs_id (user_id, f_name, l_name, date_rec) VALUES(?,?,?,?)", (user_id, f, l, dt))

    def add_subscriber_record(self, user_id, date_rec, photo, place, lat, lon):
        """Добавляем новую запись"""
        with self.connection:
            return self.cursor.execute("INSERT INTO subscribers (user_id, date_rec, photo, place, lat, lon) VALUES(?,?,?,?,?,?)", (user_id, date_rec, photo, place, lat, lon))

    def reset_user_records(self, user_id):
        """Удаляем всех пользователей"""
        with self.connection:
            return self.cursor.execute(f"DELETE FROM subscribers WHERE user_id = {user_id}")
    
    def return_users_places(self, user_id):
        """Возвращаем 10 последних записей"""
        return self.cursor.execute(f"SELECT date_rec, place, lat, lon, photo FROM subscribers WHERE user_id = {user_id} ORDER BY date_rec DESC LIMIT 10").fetchall()

    def close(self):
        """Закрываем соединение с БД"""
        self.connection.close()

db = SQLighter('telebot_base.db')

LOC_DICT = defaultdict(lambda: {})
def append_decription_loc(user_id, value):
    LOC_DICT[user_id]["location"] = value
def append_photo_loc(user_id, value):
    LOC_DICT[user_id]["photo"] = value
def get_loc(user_id):
    temp_loc = LOC_DICT[user_id]["location"]
    LOC_DICT[user_id]["location"] = None
    return temp_loc
def get_photo(user_id):
    temp_photo = LOC_DICT[user_id]["photo"]
    LOC_DICT[user_id]["photo"] = None
    return temp_photo

START, PHOTO, LOCATION, FINISH = range(4)
USER_STATE = defaultdict(lambda: START)

def get_state(message):
    return USER_STATE[message.chat.id]
def update_state(message, state):
    USER_STATE[message.chat.id] = state

@tb.message_handler(commands=['start'])
def start_message(message):
    tb.send_message(message.chat.id, f'Привет, {message.chat.first_name} {message.chat.last_name} ({message.chat.id}).\nЯ PlaceCourseraBot\n\n\nОбо мне:\nУмею сохранять интересные места\nи отправлять обратно список:) \n\nСписок команд: \n/add\n/list\n/reset')
    db.add_subscriber(message)

@tb.message_handler(commands=['add'], func = lambda message : get_state(message) == START)
def handle_description(message):
    tb.send_message(message.chat.id, text='Отправьте название места')
    LOC_DICT[message.chat.id]["location"] = None
    LOC_DICT[message.chat.id]["photo"] = None
    update_state(message, LOCATION)
    db.add_subscriber(message)
    
@tb.message_handler(func = lambda message : get_state(message) == LOCATION)
def handle_geolocation(message):
    append_decription_loc(message.chat.id, message.text)
    tb.send_message(message.chat.id, text='Отправьте фото места')
    update_state(message, PHOTO)

@tb.message_handler(content_types=['photo'], func = lambda message : get_state(message) == PHOTO)
def handle_photo(message):
    try:
        fileID = message.photo[-1].file_id
        file = tb.get_file(fileID)
        url = f"https://api.telegram.org/file/bot{token}/{file.file_path}"
        response = requests.get(url)
        append_photo_loc(message.chat.id, response.content)
        tb.send_message(message.chat.id, text='Отправьте геопозицию места')
        update_state(message, FINISH)
    except:
        tb.send_message(message.chat.id, text='Проблемы при загрузке фото...\nПовторите снова отправить фото.')

@tb.message_handler(content_types=['location'], func = lambda message : get_state(message) == FINISH)
def handle_confirmation(message):
    try:
        lat = message.location.latitude
        lon = message.location.longitude
        description = get_loc(message.chat.id)
        photo = get_photo(message.chat.id)
        db.add_subscriber_record(message.chat.id, datetime.datetime.now(), photo, description, lat, lon)
        update_state(message, START)
        tb.send_message(message.chat.id, text='Новая локация добавлена.')
    except:
        tb.send_message(message.chat.id, text='Проблемы при загрузке геопозиции...\nПовторите снова отправить геопозицию.')


@tb.message_handler(func=lambda x: True, commands=['list'])
def handle_list(message):
    list_results =  db.return_users_places(message.chat.id)
    if len(list_results) > 0:
        for idx, row in enumerate(list_results):
            dt = row[0].split(".")[0]
            info = f"{idx+1}. {row[1]}\nДобавлено: {dt}"
            tb.send_message(message.chat.id, text=info)
            tb.send_location(message.chat.id, row[2], row[3])
            tb.send_photo(message.chat.id, photo=Image.open(io.BytesIO(row[4])))
    else:
        tb.send_message(message.chat.id, text='Список локаций пуст...')

@tb.message_handler(func=lambda x: True, commands=['reset'])
def handle_reset(message):
    db.reset_user_records(user_id=message.chat.id)
    tb.send_message(message.chat.id, text='Список удален!')

tb.polling()