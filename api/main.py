import os
import uuid
import random
import datetime
from fastapi import FastAPI, HTTPException, Request
from supabase import create_client, Client
from pydantic import BaseModel
from typing import Optional

# --- ИНИЦИАЛИЗАЦИЯ ---
app = FastAPI(title="XHUB V7.1 - PyTest Edition")

# Конфигурация
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
# Твой новый короткий ключ
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "PyTest")

try:
    if not SUPABASE_URL or not SUPABASE_KEY:
        supabase: Optional[Client] = None
    else:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Supabase Error: {e}")
    supabase = None

# --- MODELS ---
class UserRegRequest(BaseModel):
    username: str
    password: str
    email: str

class UserLogin(BaseModel):
    username: str
    password: str

class PresenceUpdate(BaseModel):
    token: str
    status: str
    game: str

class FriendRequest(BaseModel):
    from_user: str
    to_user: str

# --- HELPERS ---
def check_admin(request: Request):
    key = request.headers.get('x-admin-key')
    if key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid Key")

# --- ENDPOINTS ---

@app.get("/")
async def health():
    return {
        "status": "XHUB V7.1 Online",
        "key_mode": "Short (PyTest)",
        "database": "Connected" if supabase else "Disconnected"
    }

# --- SYSTEM (FOR KEEPER) ---
@app.get("/sys/get_mail")
async def get_mail(request: Request):
    check_admin(request)
    res = supabase.table("mail_queue").select("*").eq("status", "pending").execute()
    return res.data

@app.post("/sys/confirm_mail")
async def confirm_mail(request: Request, data: dict):
    check_admin(request)
    email = data.get("email")
    supabase.table("mail_queue").delete().eq("recipient", email).execute()
    return {"status": "ok"}

# --- AUTH ---
@app.post("/auth/request_reg")
async def register(data: UserRegRequest):
    code = random.randint(100000, 999999)
    # Сразу в очередь на отправку Кипером
    mail_payload = {
        "recipient": data.email,
        "subject": "XHUB Code",
        "body": f"Code: {code} | User: {data.username}",
        "status": "pending"
    }
    supabase.table("mail_queue").insert(mail_payload).execute()
    # Создаем юзера (пока без статуса подтверждения для простоты)
    supabase.table("users").insert({
        "username": data.username, 
        "password": data.password, 
        "email": data.email
    }).execute()
    return {"status": "code_sent"}

@app.post("/auth/login")
async def login(data: UserLogin):
    res = supabase.table("users").select("*").eq("username", data.username).eq("password", data.password).execute()
    if not res.data:
        raise HTTPException(401, "Fail")
    
    token = str(uuid.uuid4())
    supabase.table("sessions").insert({"username": data.username, "token": token}).execute()
    return {"auth": True, "token": token, "username": data.username}

# --- PRESENCE & FRIENDS ---
@app.post("/presence/update")
async def update_presence(data: PresenceUpdate):
    session = supabase.table("sessions").select("username").eq("token", data.token).execute()
    if not session.data:
        raise HTTPException(403)
    
    user_name = session.data[0]['username']
    supabase.table("users").update({"status": data.status, "game": data.game}).eq("username", user_name).execute()
    return {"status": "ok"}

@app.get("/presence/list")
async def get_list():
    res = supabase.table("users").select("username, status, game").execute()
    return res.data

@app.post("/friends/add")
async def add_friend(data: FriendRequest):
    # Добавляем запись в таблицу заявок
    supabase.table("friend_requests").insert({
        "from_user": data.from_user, 
        "to_user": data.to_user,
        "status": "pending"
    }).execute()
    return {"status": "request_sent"}
