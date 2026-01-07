import os
import datetime
import uuid
import random
from fastapi import FastAPI, HTTPException, Header, Request
from supabase import create_client, Client
from pydantic import BaseModel

app = FastAPI(title="XHUB SERVER V7.0 - Supabase Production")

# Конфиги из переменных окружения Vercel
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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

# --- SYSTEM ---
@app.get("/")
async def health(): 
    return {"status": "XHUB V7 Online", "db": "Supabase Cloud"}

@app.get("/sys/get_mail")
async def get_pending_mail(request: Request):
    key = request.headers.get('x-admin-key')
    if key != ADMIN_SECRET: raise HTTPException(403)
    res = supabase.table("mail_queue").select("*").eq("status", "pending").execute()
    return res.data

@app.post("/sys/confirm_mail")
async def confirm_mail_sent(request: Request, data: dict):
    key = request.headers.get('x-admin-key')
    if key != ADMIN_SECRET: raise HTTPException(403)
    supabase.table("mail_queue").delete().eq("recipient", data.get("email")).execute()
    return {"status": "ok"}

# --- AUTH ---
@app.post("/auth/request_reg")
async def request_registration(data: UserRegRequest):
    code = random.randint(100000, 999999)
    # Используем mail_queue как временное хранилище кода (для простоты)
    mail_data = {
        "recipient": data.email,
        "subject": "XHUB Verification",
        "body": f"User: {data.username} | Code: {code} | Pass: {data.password}",
        "status": "pending"
    }
    supabase.table("mail_queue").insert(mail_data).execute()
    return {"status": "pending_verification"}

@app.post("/auth/login")
async def login(data: UserLogin):
    res = supabase.table("users").select("*").eq("username", data.username).eq("password", data.password).execute()
    if res.data:
        token = str(uuid.uuid4())
        supabase.table("sessions").insert({"username": data.username, "token": token}).execute()
        return {"auth": True, "token": token, "username": data.username}
    raise HTTPException(401, "Invalid credentials")

@app.post("/presence/update")
async def update_presence(data: PresenceUpdate):
    session = supabase.table("sessions").select("username").eq("token", data.token).execute()
    if not session.data: raise HTTPException(403)
    username = session.data[0]['username']
    supabase.table("users").update({"status": data.status, "game": data.game}).eq("username", username).execute()
    return {"status": "ok"}

@app.get("/presence/list")
async def get_friends_list():
    res = supabase.table("users").select("username, status, game").execute()
    return res.data
