import os
import uuid
import random
import datetime
from fastapi import FastAPI, HTTPException, Header, Request
from supabase import create_client, Client
from pydantic import BaseModel
from typing import List, Optional

# --- ИНИЦИАЛИЗАЦИЯ ---
app = FastAPI(title="XHUB V7.0 PRO")

# Конфигурация из Environment Variables
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "PyTest")

# Инициализация Supabase с проверкой на лету
try:
    if not SUPABASE_URL or not SUPABASE_KEY:
        supabase: Optional[Client] = None
    else:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Supabase Init Error: {e}")
    supabase = None

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

# --- HELPER FUNCTIONS ---
def check_admin_access(request: Request):
    key = request.headers.get('x-admin-key')
    if not key or key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden: Admin Access Required")

# --- ENDPOINTS ---

@app.get("/")
async def health():
    return {
        "status": "XHUB V7 Online",
        "database": "Connected" if supabase else "Disconnected",
        "time": str(datetime.datetime.now())
    }

# Системные запросы для Keeper.py
@app.get("/sys/get_mail")
async def get_pending_mail(request: Request):
    check_admin_access(request)
    if not supabase: raise HTTPException(500, "DB Not Configured")
    
    try:
        # Тянем только ожидающие отправки письма
        res = supabase.table("mail_queue").select("*").eq("status", "pending").execute()
        return res.data
    except Exception as e:
        raise HTTPException(500, f"DB Error: {str(e)}")

@app.post("/sys/confirm_mail")
async def confirm_mail_sent(request: Request, data: dict):
    check_admin_access(request)
    if not supabase: raise HTTPException(500, "DB Not Configured")
    
    email = data.get("email")
    try:
        # Удаляем письмо из очереди после успешной отправки кипером
        supabase.table("mail_queue").delete().eq("recipient", email).execute()
        return {"status": "confirmed"}
    except Exception as e:
        raise HTTPException(500, str(e))

# Авторизация и регистрация
@app.post("/auth/request_reg")
async def request_registration(data: UserRegRequest):
    if not supabase: raise HTTPException(500, "DB Not Configured")
    
    # Генерируем код подтверждения
    code = random.randint(100000, 999999)
    
    try:
        # Проверяем, нет ли уже такого юзера
        user_check = supabase.table("users").select("username").eq("username", data.username).execute()
        if user_check.data:
            raise HTTPException(400, "Username already exists")
        
        # Закидываем письмо в очередь для кипера
        mail_payload = {
            "recipient": data.email,
            "subject": "XHUB Verification Code",
            "body": f"Welcome! Your verification code: {code}\nUsername: {data.username}\nPassword: {data.password}",
            "status": "pending"
        }
        supabase.table("mail_queue").insert(mail_payload).execute()
        
        # Создаем временную запись для подтверждения (в идеале нужна таблица pending_reg)
        # Но для прототипа можно хранить код прямо в базе или памяти.
        # Давай пока просто вернем успех, предполагая, что ты создаешь юзера после кода.
        return {"status": "pending_verification", "email": data.email}
    except Exception as e:
        raise HTTPException(500, f"Registration Error: {str(e)}")

@app.post("/auth/login")
async def login(data: UserLogin):
    if not supabase: raise HTTPException(500, "DB Not Configured")
    
    try:
        res = supabase.table("users").select("*").eq("username", data.username).eq("password", data.password).execute()
        if not res.data:
            raise HTTPException(401, "Invalid credentials")
        
        token = str(uuid.uuid4())
        # Сохраняем сессию в облаке
        supabase.table("sessions").insert({"username": data.username, "token": token}).execute()
        
        return {
            "auth": True,
            "token": token,
            "username": data.username
        }
    except Exception as e:
        raise HTTPException(500, str(e))

# Статусы (Presence)
@app.post("/presence/update")
async def update_presence(data: PresenceUpdate):
    if not supabase: raise HTTPException(500, "DB Not Configured")
    
    try:
        # Проверяем токен
        session = supabase.table("sessions").select("username").eq("token", data.token).execute()
        if not session.data:
            raise HTTPException(403, "Invalid Session Token")
        
        user_name = session.data[0]['username']
        # Обновляем инфо в таблице юзеров
        supabase.table("users").update({
            "status": data.status,
            "game": data.game
        }).eq("username", user_name).execute()
        
        return {"status": "updated"}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/presence/list")
async def get_presence_list():
    if not supabase: raise HTTPException(500, "DB Not Configured")
    try:
        res = supabase.table("users").select("username, status, game").execute()
        return res.data
    except Exception as e:
        raise HTTPException(500, str(e))
