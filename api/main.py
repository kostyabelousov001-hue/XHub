import os, uuid, random
from fastapi import FastAPI, HTTPException, Request
from supabase import create_client, Client
from pydantic import BaseModel

app = FastAPI()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
ADMIN_SECRET = "PyTest"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class RegData(BaseModel):
    username: str; password: str; email: str

class VerifyData(BaseModel):
    email: str; code: str

class FriendAction(BaseModel):
    from_user: str; to_user: str; status: str = "pending"

@app.get("/")
async def health(): return {"status": "online"}

# --- AUTH ---
@app.post("/auth/request_reg")
async def request_reg(data: RegData):
    code = str(random.randint(100000, 999999))
    supabase.table("users").insert({
        "username": data.username, "password": data.password, 
        "email": data.email, "verification_code": code, "is_verified": False
    }).execute()
    supabase.table("mail_queue").insert({
        "recipient": data.email, "subject": "XHUB CODE", "body": f"Code: {code}"
    }).execute()
    return {"ok": True}

@app.post("/auth/confirm_reg")
async def confirm_reg(data: VerifyData):
    res = supabase.table("users").select("*").eq("email", data.email).eq("verification_code", data.code).execute()
    if res.data:
        # Прямое принудительное обновление
        supabase.table("users").update({"is_verified": True}).eq("email", data.email).execute()
        return {"ok": True}
    raise HTTPException(400, "Wrong code")

@app.post("/auth/login")
async def login(data: dict):
    res = supabase.table("users").select("*").eq("username", data['username']).eq("password", data['password']).eq("is_verified", True).execute()
    if not res.data: raise HTTPException(401, "Denied")
    token = str(uuid.uuid4())
    supabase.table("sessions").insert({"username": data['username'], "token": token}).execute()
    return {"auth": True, "token": token, "username": data['username']}

# --- SOCIAL ---
@app.post("/friends/add")
async def add_f(data: FriendAction):
    # Проверка на дубликат заявки
    exist = supabase.table("friend_requests").select("*").eq("from_user", data.from_user).eq("to_user", data.to_user).execute()
    if exist.data: return {"status": "already_exists"}
    supabase.table("friend_requests").insert({"from_user": data.from_user, "to_user": data.to_user}).execute()
    return {"ok": True}

@app.post("/friends/my_requests")
async def my_req(data: dict):
    res = supabase.table("friend_requests").select("*").eq("to_user", data['username']).execute()
    return res.data

@app.post("/friends/respond")
async def respond(data: FriendAction):
    if data.status == "accepted":
        # Создаем связь и удаляем заявку
        supabase.table("friendships").insert({"user1": data.from_user, "user2": data.to_user}).execute()
    supabase.table("friend_requests").delete().eq("from_user", data.from_user).eq("to_user", data.to_user).execute()
    return {"ok": True}

# --- SYSTEM (KEEPER) ---
@app.get("/sys/get_mail")
async def get_m(request: Request):
    if request.headers.get("x-admin-key") == ADMIN_SECRET:
        return supabase.table("mail_queue").select("*").eq("status", "pending").execute().data
    raise HTTPException(403)

@app.post("/sys/confirm_mail")
async def conf_m(request: Request, data: dict):
    if request.headers.get("x-admin-key") == ADMIN_SECRET:
        supabase.table("mail_queue").delete().eq("recipient", data['email']).execute()
        return {"ok": True}
