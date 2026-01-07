import os, uuid, random, datetime
from fastapi import FastAPI, HTTPException, Request
from supabase import create_client, Client
from pydantic import BaseModel
from typing import Optional

app = FastAPI()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
ADMIN_SECRET = "PyTest"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class RegReq(BaseModel): username: str; password: str; email: str
class ConfirmReq(BaseModel): email: str; code: str
class PresenceReq(BaseModel): token: str; status: str; game: str
class FriendReq(BaseModel): from_user: str; to_user: str; status: Optional[str] = "pending"
class MsgReq(BaseModel): token: str; recipient: str; content: str
class MsgPoll(BaseModel): token: str; last_id: int
class HistoryReq(BaseModel): token: str; other_user: str

def get_user(token):
    res = supabase.table("sessions").select("username").eq("token", token).execute()
    return res.data[0]['username'] if res.data else None

@app.get("/")
async def root(): return {"status": "Online"}

@app.post("/auth/request_reg")
async def req_reg(d: RegReq):
    code = str(random.randint(100000, 999999))
    supabase.table("users").insert({"username": d.username, "password": d.password, "email": d.email, "verification_code": code}).execute()
    supabase.table("mail_queue").insert({"recipient": d.email, "subject": "XHUB Code", "body": f"Code: {code}"}).execute()
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
    if not res.data: raise HTTPException(401, "Auth failed")
    token = str(uuid.uuid4())
    supabase.table("sessions").insert({"username": d['username'], "token": token}).execute()
    return {"auth": True, "token": token, "username": d['username']}

@app.post("/presence/update")
async def upd_p(d: PresenceReq):
    u = get_user(d.token)
    if u: supabase.table("users").update({"status": d.status, "game": d.game}).eq("username", u).execute()
    return {"ok": True}

@app.get("/presence/list")
async def get_l(): return supabase.table("users").select("username, status, game").eq("is_verified", True).execute().data

# --- FRIENDS ---
@app.post("/friends/add")
async def add_f(d: FriendReq):
    # Проверка на дубликаты
    exists = supabase.table("friend_requests").select("*").eq("from_user", d.from_user).eq("to_user", d.to_user).execute()
    if not exists.data:
        supabase.table("friend_requests").insert({"from_user": d.from_user, "to_user": d.to_user}).execute()
    return {"ok": True}

@app.post("/friends/my_requests")
async def get_my_r(d: dict): return supabase.table("friend_requests").select("*").eq("to_user", d['username']).eq("status", "pending").execute().data

@app.post("/friends/respond")
async def resp_f(d: FriendReq):
    if d.status == "accepted": supabase.table("friendships").insert({"user1": d.from_user, "user2": d.to_user}).execute()
    supabase.table("friend_requests").delete().eq("from_user", d.from_user).eq("to_user", d.to_user).execute()
    return {"ok": True}

@app.post("/friends/remove")
async def remove_f(d: dict):
    # Удаляем дружбу в обе стороны (user1-user2 или user2-user1)
    u1, u2 = d['user1'], d['user2']
    supabase.table("friendships").delete().or_(f"and(user1.eq.{u1},user2.eq.{u2}),and(user1.eq.{u2},user2.eq.{u1})").execute()
    return {"ok": True}

# --- CHAT ---
@app.post("/chat/send")
async def send_msg(d: MsgReq):
    sender = get_user(d.token)
    if not sender: raise HTTPException(401)
    supabase.table("messages").insert({"sender": sender, "recipient": d.recipient, "content": d.content}).execute()
    return {"ok": True}

@app.post("/chat/poll")
async def poll_msg(d: MsgPoll):
    u = get_user(d.token)
    if not u: raise HTTPException(401)
    return supabase.table("messages").select("*").or_(f"sender.eq.{u},recipient.eq.{u}").gt("id", d.last_id).order("id").execute().data

@app.post("/chat/history")
async def get_history(d: HistoryReq):
    u = get_user(d.token)
    if not u: raise HTTPException(401)
    return supabase.table("messages").select("*").or_(f"and(sender.eq.{u},recipient.eq.{d.other_user}),and(sender.eq.{d.other_user},recipient.eq.{u})").order("id").execute().data

# --- SYS ---
@app.get("/sys/get_mail")
async def get_m(r: Request):
    if r.headers.get("x-admin-key") == ADMIN_SECRET: return supabase.table("mail_queue").select("*").execute().data
    raise HTTPException(403)

@app.post("/sys/confirm_mail")
async def del_m(r: Request, d: dict):
    if r.headers.get("x-admin-key") == ADMIN_SECRET: supabase.table("mail_queue").delete().eq("recipient", d['email']).execute()
    return {"ok": True}
