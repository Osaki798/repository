# -*- coding: utf-8 -*-
"""NOVA local messenger server. Standard library only; persistent local JSON storage."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import json, os, time, uuid, hashlib, secrets, mimetypes, threading, base64

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
MEDIA_DIR = os.path.join(BASE, "media")
DB_FILE = os.path.join(DATA_DIR, "nova_data.json")
WEB_FILE = os.path.join(BASE, "web", "index.html")
MAX_FILE = 15 * 1024 * 1024

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)
lock = threading.RLock()
sessions = {}
db = {"users": {}, "messages": [], "next_id": 1}

def load_db():
    global db
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            db.update(saved)
    except (OSError, ValueError):
        pass

def save_db():
    with lock:
        tmp = DB_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DB_FILE)

def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 180000).hex()
    return salt, digest

def safe_user(value):
    return str(value or "").strip()

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def send_bytes(self, status, body, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        self.send_bytes(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 22 * 1024 * 1024:
            raise ValueError("Слишком большой запрос")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def current_user(self):
        token = self.headers.get("X-NOVA-Token", "")
        with lock:
            username = sessions.get(token)
            if username and username in db["users"]:
                db["users"][username]["last_seen"] = time.time()
                return username
        return None

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-NOVA-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            try:
                with open(WEB_FILE, "rb") as f:
                    return self.send_bytes(200, f.read(), "text/html; charset=utf-8")
            except OSError:
                return self.send_json(500, {"error": "Не найден интерфейс приложения"})
        if parsed.path == "/api/health":
            return self.send_json(200, {"ok": True})
        if parsed.path == "/api/users":
            me = self.current_user()
            if not me:
                return self.send_json(401, {"error": "Войдите в аккаунт"})
            with lock:
                users = []
                for key, item in db["users"].items():
                    if key == me:
                        continue
                    users.append({"username": item["username"], "online": time.time() - item.get("last_seen", 0) < 25})
            users.sort(key=lambda x: (not x["online"], x["username"].lower()))
            return self.send_json(200, {"users": users})
        if parsed.path == "/api/history":
            me = self.current_user()
            if not me:
                return self.send_json(401, {"error": "Войдите в аккаунт"})
            other = safe_user(parse_qs(parsed.query).get("with", [""])[0]).lower()
            with lock:
                rows = [m for m in db["messages"] if
                        (m["sender"].lower() == me and m["recipient"].lower() == other) or
                        (m["sender"].lower() == other and m["recipient"].lower() == me)]
            return self.send_json(200, {"messages": rows[-500:]})
        if parsed.path == "/api/poll":
            me = self.current_user()
            if not me:
                return self.send_json(401, {"error": "Войдите в аккаунт"})
            after = int(parse_qs(parsed.query).get("after", ["0"])[0] or 0)
            with lock:
                rows = [m for m in db["messages"] if m["id"] > after and
                        (m["sender"].lower() == me or m["recipient"].lower() == me)]
            return self.send_json(200, {"messages": rows})
        if parsed.path == "/media":
            file_id = os.path.basename(parse_qs(parsed.query).get("id", [""])[0])
            path = os.path.join(MEDIA_DIR, file_id)
            if not file_id or not os.path.isfile(path):
                return self.send_json(404, {"error": "Файл не найден"})
            with open(path, "rb") as f:
                body = f.read()
            return self.send_bytes(200, body, mimetypes.guess_type(path)[0] or "application/octet-stream")
        return self.send_json(404, {"error": "Не найдено"})

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            data = self.read_json()
        except Exception:
            return self.send_json(400, {"error": "Не удалось прочитать запрос"})
        if parsed.path == "/api/register":
            username = safe_user(data.get("username"))
            password = str(data.get("password") or "")
            if not (3 <= len(username) <= 20) or not all(c.isalnum() or c in "_-" for c in username):
                return self.send_json(400, {"error": "Логин: 3–20 символов, только буквы, цифры, _ и -"})
            if len(password) < 4:
                return self.send_json(400, {"error": "Пароль должен быть не короче 4 символов"})
            key = username.lower()
            with lock:
                if key in db["users"]:
                    return self.send_json(409, {"error": "Такой логин уже занят"})
                salt, digest = hash_password(password)
                db["users"][key] = {"username": username, "salt": salt, "password": digest, "last_seen": time.time()}
                token = secrets.token_urlsafe(32)
                sessions[token] = key
                save_db()
            return self.send_json(200, {"token": token, "username": username})
        if parsed.path == "/api/login":
            username = safe_user(data.get("username"))
            password = str(data.get("password") or "")
            key = username.lower()
            with lock:
                item = db["users"].get(key)
                if not item:
                    return self.send_json(401, {"error": "Неверный логин или пароль"})
                _, digest = hash_password(password, item["salt"])
                if not secrets.compare_digest(digest, item["password"]):
                    return self.send_json(401, {"error": "Неверный логин или пароль"})
                item["last_seen"] = time.time()
                token = secrets.token_urlsafe(32)
                sessions[token] = key
                save_db()
            return self.send_json(200, {"token": token, "username": item["username"]})
        me = self.current_user()
        if not me:
            return self.send_json(401, {"error": "Сессия закончилась. Войдите снова"})
        if parsed.path == "/api/send":
            recipient = safe_user(data.get("recipient")).lower()
            message = str(data.get("text") or "").strip()
            if not message:
                return self.send_json(400, {"error": "Напишите сообщение"})
            if len(message) > 5000:
                return self.send_json(400, {"error": "Сообщение слишком длинное"})
            with lock:
                if recipient not in db["users"]:
                    return self.send_json(404, {"error": "Пользователь не найден"})
                row = {"id": db["next_id"], "sender": db["users"][me]["username"],
                       "recipient": db["users"][recipient]["username"], "text": message,
                       "time": time.time(), "file_id": None, "file_name": None, "file_type": None}
                db["next_id"] += 1
                db["messages"].append(row)
                save_db()
            return self.send_json(200, {"message": row})
        if parsed.path == "/api/upload":
            recipient = safe_user(data.get("recipient")).lower()
            filename = os.path.basename(str(data.get("filename") or "file"))
            mime = str(data.get("mime") or "application/octet-stream")
            encoded = str(data.get("content") or "")
            if recipient not in db["users"]:
                return self.send_json(404, {"error": "Пользователь не найден"})
            try:
                raw = base64.b64decode(encoded, validate=True)
            except Exception:
                return self.send_json(400, {"error": "Файл повреждён"})
            if not raw or len(raw) > MAX_FILE:
                return self.send_json(400, {"error": "Файл должен быть не больше 15 МБ"})
            file_id = uuid.uuid4().hex
            with open(os.path.join(MEDIA_DIR, file_id), "wb") as f:
                f.write(raw)
            with lock:
                row = {"id": db["next_id"], "sender": db["users"][me]["username"],
                       "recipient": db["users"][recipient]["username"], "text": "",
                       "time": time.time(), "file_id": file_id, "file_name": filename,
                       "file_type": mime}
                db["next_id"] += 1
                db["messages"].append(row)
                save_db()
            return self.send_json(200, {"message": row})
        return self.send_json(404, {"error": "Не найдено"})

def create_server(address=("0.0.0.0", 8765)):
    load_db()
    return ThreadingHTTPServer(address, Handler)

if __name__ == "__main__":
    httpd = create_server()
    print("NOVA server running on port 8765")
    httpd.serve_forever()
