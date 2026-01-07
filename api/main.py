# app.py - XHUB SERVER V6.0 (Passive Core)
import uuid
import random
import datetime
import os
import threading
from fastapi import FastAPI, HTTPException, Response, Header as HeaderParams
from tinydb import TinyDB, Query
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="XHUB SERVER V6.0")
db_lock = threading.Lock()

ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "admin_key_123")

# --- DATABASE ---
db = TinyDB('xhub_data.json')
users_table = db.table('users')
sessions_table = db.table('sessions')
pending_table = db.table('pending_reg')
mail_queue = db.table('mail_queue') # <--- НОВАЯ ТАБЛИЦА: Очередь писем
User = Query()

# --- MODELS ---
class UserRegRequest(BaseModel):
    username: str
    password: str
    email: str

class VerifyCode(BaseModel):
    email: str
    code: int

class UserLogin(BaseModel):
    username: str
    password: str

class PresenceUpdate(BaseModel):
    token: str
    status: str
    game: str

# --- API ---

@app.get("/")
def health(): return {"status": "XHUB V6 Online", "mode": "Passive Mail"}

@app.post("/auth/request_reg")
def request_registration(data: UserRegRequest):
    with db_lock:
        if users_table.search(User.username == data.username):
            raise HTTPException(400, "Username taken")
        if users_table.search(User.email == data.email):
            raise HTTPException(400, "Email already used")

        code = random.randint(100000, 999999)
        
        # 1. Сохраняем код
        pending_table.upsert({
            "username": data.username,
            "password": data.password, 
            "email": data.email,
            "code": code
        }, User.email == data.email)

        # 2. Добавляем задачу в очередь писем для Кипера
        mail_queue.insert({
            "to": data.email,
            "subject": "XHUB Code",
            "body": f"Code: {code}",
            "status": "pending",
            "created_at": str(datetime.datetime.now())
        })

    return {"status": "Request queued"}

@app.post("/auth/confirm_reg")
def confirm_registration(data: VerifyCode):
    with db_lock:
        record = pending_table.get(User.email == data.email)
        if not record or record['code'] != data.code:
            raise HTTPException(400, "Invalid code")

        users_table.insert({
            "id": str(uuid.uuid4()),
            "username": record['username'],
            "password": record['password'],
            "email": record['email'],
            "status": "Online", "game": "Newbie"
        })
        pending_table.remove(User.email == data.email)
    return {"status": "User created"}

# --- Эндпоинты для Кипера (Почтальона) ---

@app.get("/sys/get_mail")
def get_pending_mail(x_admin_key: str = HeaderParams(None)):
    """Кипер забирает письма, которые надо отправить"""
    if x_admin_key != ADMIN_SECRET: raise HTTPException(403)
    # Отдаем только те, что 'pending'
    return mail_queue.search(Query().status == "pending")

@app.post("/sys/confirm_mail")
def confirm_mail_sent(data: dict, x_admin_key: str = HeaderParams(None)):
    """Кипер отчитывается, что отправил письмо"""
    if x_admin_key != ADMIN_SECRET: raise HTTPException(403)
    email = data.get("email")
    # Удаляем из очереди, раз отправлено
    with db_lock:
        mail_queue.remove(Query().to == email)
    return {"status": "ok"}

# (Остальные эндпоинты Login/Presence такие же, как были)
@app.post("/auth/login")
def login(data: UserLogin):
    with db_lock:
        user = users_table.get((User.username == data.username) & (User.password == data.password))
        if user:
            token = str(uuid.uuid4())
            sessions_table.insert({"token": token, "username": user['username']})
            return {"auth": True, "token": token, "username": user['username']}
    raise HTTPException(401, "Bad credentials")

@app.post("/presence/update")
def update_presence(data: PresenceUpdate):
    with db_lock:
        session = sessions_table.get(User.token == data.token)
        if not session: raise HTTPException(403)
        users_table.update({"status": data.status, "game": data.game}, User.username == session['username'])
    return {"status": "ok"}

@app.get("/presence/list")
def get_friends_list():
    return users_table.all()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
