import uuid
import random
import datetime
import os
import threading
from fastapi import FastAPI, HTTPException, Header, Request
from tinydb import TinyDB, Query
from pydantic import BaseModel

# --- ИНИЦИАЛИЗАЦИЯ ---
app = FastAPI(title="XHUB SERVER V6.0 - Vercel Mirror")
db_lock = threading.Lock()

# Берем секрет из переменных окружения Vercel
# Если его там нет, будет использовано дефолтное значение (проверь настройки в Dashboard!)
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "7#x!Lp@9Qz$3Rk&Yv%Pw*1sN5dF8^A2mG+U4jT6hX0cB?Z/S(e)oV{I}lK-nW<M>rC:yD;gH=b|q")

# --- DATABASE ---
# Vercel разрешает запись только в /tmp. Вне этой папки будет 500 ошибка.
db_path = '/tmp/xhub_data.json' if os.environ.get('VERCEL') else 'xhub_data.json'
db = TinyDB(db_path)
users_table = db.table('users')
sessions_table = db.table('sessions')
pending_table = db.table('pending_reg')
mail_queue = db.table('mail_queue')
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

# --- SYSTEM ENDPOINTS ---

@app.get("/")
async def health(): 
    return {
        "status": "XHUB V6 Online", 
        "mode": "Vercel Mirror", 
        "node": "Production",
        "timestamp": str(datetime.datetime.now())
    }

@app.get("/sys/get_mail")
async def get_pending_mail(request: Request):
    # Прямое извлечение заголовка для обхода проблем с регистром
    client_key = request.headers.get('x-admin-key')
    
    if not client_key or client_key != ADMIN_SECRET:
        # В логи Vercel (виртуальные) уйдет инфо о попытке без палева самого ключа
        print(f"DEBUG: Auth Failed. Header: {bool(client_key)}")
        raise HTTPException(status_code=403, detail="Forbidden: Admin Key Mismatch")
        
    return mail_queue.search(Query().status == "pending")

@app.post("/sys/confirm_mail")
async def confirm_mail_sent(request: Request, data: dict):
    client_key = request.headers.get('x-admin-key')
    if not client_key or client_key != ADMIN_SECRET:
        raise HTTPException(403)
        
    email = data.get("email")
    with db_lock:
        mail_queue.remove(Query().to == email)
    return {"status": "ok"}

# --- AUTH & PRESENCE ---

@app.post("/auth/request_reg")
async def request_registration(data: UserRegRequest):
    with db_lock:
        if users_table.search(User.username == data.username):
            raise HTTPException(400, "Username taken")
        code = random.randint(100000, 999999)
        pending_table.upsert({
            "username": data.username, "password": data.password, 
            "email": data.email, "code": code
        }, User.email == data.email)
        mail_queue.insert({
            "to": data.email, "subject": "XHUB Code", "body": f"Code: {code}",
            "status": "pending", "created_at": str(datetime.datetime.now())
        })
    return {"status": "Request queued"}

@app.post("/auth/confirm_reg")
async def confirm_registration(data: VerifyCode):
    with db_lock:
        record = pending_table.get(User.email == data.email)
        if not record or record['code'] != data.code:
            raise HTTPException(400, "Invalid code")
        users_table.insert({
            "id": str(uuid.uuid4()), "username": record['username'],
            "password": record['password'], "email": record['email'],
            "status": "Online", "game": "Newbie"
        })
        pending_table.remove(User.email == data.email)
    return {"status": "User created"}

@app.post("/auth/login")
async def login(data: UserLogin):
    with db_lock:
        user = users_table.get((User.username == data.username) & (User.password == data.password))
        if user:
            token = str(uuid.uuid4())
            sessions_table.insert({"token": token, "username": user['username']})
            return {"auth": True, "token": token, "username": user['username']}
    raise HTTPException(401, "Bad credentials")

@app.post("/presence/update")
async def update_presence(data: PresenceUpdate):
    with db_lock:
        session = sessions_table.get(User.token == data.token)
        if not session: raise HTTPException(403)
        users_table.update({"status": data.status, "game": data.game}, User.username == session['username'])
    return {"status": "ok"}

@app.get("/presence/list")
async def get_friends_list():
    return users_table.all()
