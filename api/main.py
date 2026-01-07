import os
import uuid
import random
import datetime
from fastapi import FastAPI, HTTPException, Request
from supabase import create_client, Client
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()

# --- CONFIG ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
ADMIN_SECRET = "PyTest"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- MODELS ---
class RegReq(BaseModel):
    username: str
    password: str
    email: str

class ConfirmReq(BaseModel):
    email: str
    code: str

class PresenceReq(BaseModel):
    token: str
    status: str
    game: str

class FriendReq(BaseModel):
    from_user: str
    to_user: str
    status: Optional[str] = "pending"

class MsgReq(BaseModel):
    token: str
    recipient: str
    content: str

class MsgPoll(BaseModel):
    token: str
    last_id: int

# --- HELPERS ---
def get_user_by_token(token: str):
    res = supabase.table("sessions").select("username").eq("token", token).execute()
    if not res.data:
        return None
    return res.data[0]['username']

# --- AUTH ENDPOINTS ---
@app.post("/auth/request_reg")
async def req_reg(d: RegReq):
    code = str(random.randint(100000, 999999))
    supabase.table("users").insert({
        "username": d.username, 
        "password": d.password, 
        "email": d.email, 
        "verification_code": code
    }).execute()
    # Queue mail for local Keeper
    supabase.table("mail_queue").insert({
        "recipient": d.email, 
        "subject": "XHUB Code", 
        "body": f"Code: {code}"
    }).execute()
    return {"ok": True}

@app.post("/auth/confirm_reg")
async def conf_reg(d: ConfirmReq):
    res = supabase.table("users").select("*").eq("email", d.email).eq("verification_code", d.code).execute()
    if res.data:
        supabase.table("users").update({"is_verified": True}).eq("email", d.email).execute()
        return {"ok": True}
    raise HTTPException(400, "Invalid code")

@app.post("/auth/login")
async def login(d: dict):
    res = supabase.table("users").select("*").eq("username", d['username']).eq("password", d['password']).eq("is_verified", True).execute()
    if not res.data:
        raise HTTPException(401, "Auth failed")
    token = str(uuid.uuid4())
    supabase.table("sessions").insert({"username": d['username'], "token": token}).execute()
    return {"auth": True, "token": token, "username": d['username']}

# --- PRESENCE ENDPOINTS ---
@app.post("/presence/update")
async def upd_p(d: PresenceReq):
    u = get_user_by_token(d.token)
    if u:
        supabase.table("users").update({"status": d.status, "game": d.game}).eq("username", u).execute()
        return {"ok": True}
    raise HTTPException(403)

@app.get("/presence/list")
async def get_l():
    return supabase.table("users").select("username, status, game").eq("is_verified", True).execute().data

# --- FRIEND ENDPOINTS ---
@app.post("/friends/add")
async def add_f(d: FriendReq):
    supabase.table("friend_requests").insert({"from_user": d.from_user, "to_user": d.to_user}).execute()
    return {"ok": True}

@app.post("/friends/my_requests")
async def get_my_r(d: dict):
    return supabase.table("friend_requests").select("*").eq("to_user", d['username']).eq("status", "pending").execute().data

@app.post("/friends/respond")
async def resp_f(d: FriendReq):
    if d.status == "accepted":
        supabase.table("friendships").insert({"user1": d.from_user, "user2": d.to_user}).execute()
    supabase.table("friend_requests").delete().eq("from_user", d.from_user).eq("to_user", d.to_user).execute()
    return {"ok": True}

# --- CHAT ENDPOINTS (NEW) ---
@app.post("/chat/send")
async def send_msg(d: MsgReq):
    sender = get_user_by_token(d.token)
    if not sender:
        raise HTTPException(401)
    supabase.table("messages").insert({
        "sender": sender,
        "recipient": d.recipient,
        "content": d.content
    }).execute()
    return {"ok": True}

@app.post("/chat/poll")
async def poll_msg(d: MsgPoll):
    user = get_user_by_token(d.token)
    if not user:
        raise HTTPException(401)
    
    # Logic: Get msgs where (Sender=Me OR Recipient=Me) AND ID > Last_ID
    # Note: Supabase complex filters via API can be tricky, using OR syntax
    res = supabase.table("messages").select("*")\
        .or_(f"sender.eq.{user},recipient.eq.{user}")\
        .gt("id", d.last_id)\
        .order("id")\
        .execute()
    return res.data

# --- SYSTEM ENDPOINTS (Keeper) ---
@app.get("/sys/get_mail")
async def get_m(r: Request):
    if r.headers.get("x-admin-key") == ADMIN_SECRET:
        return supabase.table("mail_queue").select("*").execute().data
    raise HTTPException(403)

@app.post("/sys/confirm_mail")
async def del_m(r: Request, d: dict):
    if r.headers.get("x-admin-key") == ADMIN_SECRET:
        supabase.table("mail_queue").delete().eq("recipient", d['email']).execute()
    return {"ok": True}
