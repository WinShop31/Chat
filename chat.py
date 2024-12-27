import asyncio
import sqlite3
from datetime import datetime, timedelta
import os
import json

from pywebio import start_server
from pywebio.input import *
from pywebio.output import *
from pywebio.session import run_async, run_js

online_users = set()
DB_FILE = "chat_messages.db"
USERS_FILE = "users.json"
MAX_MESSAGES_COUNT = 100
MESSAGE_LIFETIME_DAYS = 2

# Инициализация базы данных и файлов
def init_system():
    # Инициализация базы сообщений
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            message TEXT,
            timestamp DATETIME
        )
    """)
    conn.commit()
    conn.close()

    # Инициализация файла пользователей
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w') as f:
            json.dump({}, f)

# Сохранение пользователя в файл
def save_user(user_id, nickname):
    with open(USERS_FILE, 'r+') as f:
        users = json.load(f)
        users[user_id] = nickname
        f.seek(0)
        json.dump(users, f)
        f.truncate()

# Загрузка пользователя из файла
def load_user(user_id):
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            users = json.load(f)
            return users.get(user_id, None)
    return None

# Сохранение сообщения в базу данных
def save_message(username, message):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (username, message, timestamp) VALUES (?, ?, ?)", 
                   (username, message, datetime.now()))
    conn.commit()
    conn.close()

# Удаление устаревших сообщений
def delete_old_messages():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cutoff = datetime.now() - timedelta(days=MESSAGE_LIFETIME_DAYS)
    cursor.execute("DELETE FROM messages WHERE timestamp < ?", (cutoff,))
    conn.commit()
    conn.close()

# Загрузка всех сообщений из базы данных
def load_messages():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT username, message FROM messages ORDER BY id")
    messages = cursor.fetchall()
    conn.close()
    return messages

async def login():
    session_id = run_js("localStorage.getItem('session_id');")
    if session_id is None:
        session_id = run_js("localStorage.setItem('session_id', Math.random().toString(36).substr(2));")

    # Проверка, заходил ли пользователь ранее
    nickname = load_user(session_id)
    if nickname:
        toast(f"Добро пожаловать обратно, {nickname}!")
        await main(nickname)
    else:
        # Регистрация нового пользователя
        nickname = await input("Заполните профиль", placeholder="Введите ваш псевдоним", required=True)
        save_user(session_id, nickname)
        toast("Профиль сохранен!")
        await main(nickname)

async def main(nickname):
    global online_users

    put_markdown(f"## 🧊 Добро пожаловать в онлайн чат, {nickname}!\nСообщения сохраняются на 2 дня!")

    msg_box = output()
    put_scrollable(msg_box, height=300, keep_bottom=True)

    # Загрузка сохраненных сообщений
    delete_old_messages()
    saved_messages = load_messages()
    for user, message in saved_messages:
        msg_box.append(put_markdown(f"`{user}`: {message}"))

    online_users.add(nickname)
    save_message('📢', f'`{nickname}` присоединился к чату!')
    msg_box.append(put_markdown(f'📢 `{nickname}` присоединился к чату'))

    # Если пользователь администратор, добавляем кнопку для очистки чата
    if nickname == "Systemadmin9282911923838":
        put_buttons(["Очистить чат"], onclick=lambda btn: clear_chat())

    refresh_task = run_async(refresh_msg(nickname, msg_box))

    while True:
        data = await input_group("💭 Новое сообщение", [
            input(placeholder="Текст сообщения ...", name="msg"),
            actions(name="cmd", buttons=["Отправить", {'label': "Выйти из чата", 'type': 'cancel'}])
        ], validate=lambda m: ('msg', "Введите текст сообщения!") if m["cmd"] == "Отправить" and not m['msg'] else None)

        if data is None:
            break

        save_message(nickname, data['msg'])
        msg_box.append(put_markdown(f"`{nickname}`: {data['msg']}"))

    refresh_task.close()

    online_users.remove(nickname)
    toast("Вы вышли из чата!")
    save_message('📢', f'Пользователь `{nickname}` покинул чат!')
    msg_box.append(put_markdown(f'📢 Пользователь `{nickname}` покинул чат!'))

    put_buttons(['Перезайти'], onclick=lambda btn: run_js('window.location.reload()'))

async def refresh_msg(nickname, msg_box):
    last_idx = len(load_messages())

    while True:
        await asyncio.sleep(1)

        delete_old_messages()
        new_messages = load_messages()[last_idx:]
        for user, message in new_messages:
            if user != nickname:
                msg_box.append(put_markdown(f"`{user}`: {message}"))
        last_idx = len(load_messages())

def clear_chat():
    # Очистка базы данных (удаление всех сообщений)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages")
    conn.commit()
    conn.close()

    # Очистка сообщений на экране
    run_js("document.querySelector('.pywebio-output').innerHTML = '';")
    toast("Чат очищен!")

if __name__ == "__main__":
    init_system()
    start_server(login, debug=True, port=8080, cdn=False)
