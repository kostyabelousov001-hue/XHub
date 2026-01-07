import os
import uuid
import random
import datetime
from fastapi import FastAPI, HTTPException, Request
from supabase import create_client, Client
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="XHUB CORE SERVER V8.1")

# --- ИНИЦИАЛИЗАЦИЯ ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
ADMIN_SECRET = "PyTest"

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Supabase Init Error: {e}")
    supabase = None

# --- MODELS ---
class RegRequest(BaseModel):
    username: str
    password: str
    email: str

class VerifyRequest(BaseModel):
    email: str
    code: str

class LoginRequest(BaseModel):
    username: str
    password: str

class PresenceUpdate(BaseModel):
    token: str
    status: str
    game: str

class FriendAction(BaseModel):
    from_user: str
    to_user: str
    status: Optional[str] = "pending"

# --- HELPER: АДМИН ДОСТУП ---
def check_admin(request: Request):
    key = request.headers.get('x-admin-key')
    if key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden: PyTest key required")

# --- ROUTES: AUTH ---

@app.get("/")
async def health():
    return {"status": "XHUB_CORE_ONLINE", "db": "OK" if supabase else "FAIL"}

@app.post("/auth/request_reg")
async def request_reg(data: RegRequest):
    # 1. Генерим код
    code = str(random.randint(100000, 999999))
    try:
        # 2. Создаем запись (is_verified = False)
        supabase.table("users").insert({
            "username": data.username, 
            "password": data.password, 
            "email": data.email,
            "verification_code": code,
            "is_verified": False
        }).execute()
        
        # 3. Ставим задачу Киперу в очередь
        supabase.table("mail_queue").insert({
            "recipient": data.email,
            "subject": "XHUB Verification Code",
            "body": f"Welcome to XHUB, {data.username}! Your code: {code}",
            "status": "pending"
        }).execute()
        
        return {"status": "code_sent"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/auth/confirm_reg")
async def confirm_reg(data: VerifyRequest):
    # Проверяем код
    res = supabase.table("users").select("*").eq("email", data.email).eq("verification_code", data.code).execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Invalid verification code")
    
    # Активируем аккаунт
    supabase.table("users").update({"is_verified": True}).eq("email", data.email).execute()
    return {"status": "account_activated"}

@app.post("/auth/login")
async def login(data: LoginRequest):
    res = supabase.table("users").select("*").eq("username", data.username).eq("password", data.password).eq("is_verified", True).execute()
    if not res.data:
        raise HTTPException(status_code=401, detail="Invalid credentials or account not verified")
    
    token = str(uuid.uuid4())
    supabase.table("sessions").insert({"username": data.username, "token": token}).execute()
    return {"auth": True, "token": token, "username": data.username}

# --- ROUTES: SOCIAL & PRESENCE ---

@app.post("/presence/update")
async def update_presence(data: PresenceUpdate):
    session = supabase.table("sessions").select("username").eq("token", data.token).execute()
    if not session.data:
        raise HTTPException(status_code=403, detail="Invalid Token")
    
    user_name = session.data[0]['username']
    supabase.table("users").update({"status": data.status, "game": data.game}).eq("username", user_name).execute()
    return {"status": "presence_updated"}

@app.get("/presence/list")
async def get_presence_list():
    res = supabase.table("users").select("username, status, game").eq("is_verified", True).execute()
    return res.data

@app.post("/friends/add")
async def add_friend(data: FriendAction):
    supabase.table("friend_requests").insert({
        "from_user": data.from_user, 
        "to_user": data.to_user, 
        "status": "pending"
    }).execute()
    return {"status": "request_sent"}

@app.post("/friends/my_requests")
async def get_my_requests(data: dict):
    # Юзер передает свой username, получаем входящие заявки
    username = data.get("username")
    res = supabase.table("friend_requests").select("*").eq("to_user", username).eq("status", "pending").execute()
    return res.data

@app.post("/friends/respond")
async def respond_friend(data: FriendAction):
    # data.status должен быть 'accepted' или 'declined'
    supabase.table("friend_requests").update({"status": data.status}).eq("from_user", data.from_user).eq("to_user", data.to_user).execute()
    return {"status": f"request_{data.status}"}

# --- ROUTES: SYSTEM (KEEPER ONLY) ---

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
    return {"status": "cleared"}
