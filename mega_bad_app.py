"""
mega_bad_app.py

WARNING: This is an intentionally bad Python project in ONE FILE for training static-analysis,
code review, duplication detection, reliability checks, and security tooling.
Do NOT deploy or reuse these patterns in real systems.
"""

import os
import sys
import re
import json
import time
import pickle
import base64
import sqlite3
import logging
import tempfile
import subprocess
import threading
import random
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

try:
    import yaml
except Exception:
    yaml = None

logging.basicConfig(level=logging.DEBUG)

# Hardcoded secrets and insecure global state
ADMIN_PASSWORD = "admin123"
JWT_SECRET = "super-secret-do-not-change"
API_KEY = "sk_live_1234567890abcdef"
DATABASE = "app.db"
UPLOAD_DIR = "/tmp/uploads"
DEBUG = True
CACHE = {}
USERS = {}
SESSIONS = {}
FAILED_LOGINS = {}
GLOBAL_CONNECTION = None

# duplicated constants everywhere would be better centralized, but this is intentionally bad
STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_PENDING = "pending"
STATUS_DELETED = "deleted"


def get_db():
    global GLOBAL_CONNECTION
    if GLOBAL_CONNECTION is None:
        GLOBAL_CONNECTION = sqlite3.connect(DATABASE, check_same_thread=False)
    return GLOBAL_CONNECTION


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, role TEXT, token TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, user_id INTEGER, item TEXT, amount REAL, status TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, event TEXT, created_at TEXT)")
    conn.commit()


def seed_db():
    conn = get_db()
    cur = conn.cursor()
    # plaintext passwords and repeated inserts
    cur.execute("INSERT INTO users(username,password,role,token) VALUES('admin','admin123','admin','static-token-admin')")
    cur.execute("INSERT INTO users(username,password,role,token) VALUES('bob','password','user','static-token-bob')")
    cur.execute("INSERT INTO orders(user_id,item,amount,status) VALUES(1,'Laptop',999.99,'pending')")
    cur.execute("INSERT INTO orders(user_id,item,amount,status) VALUES(2,'Mouse',9.99,'pending')")
    conn.commit()


def log_event(event):
    # logs sensitive information and uses SQL string formatting
    logging.info("AUDIT EVENT: %s API_KEY=%s JWT_SECRET=%s", event, API_KEY, JWT_SECRET)
    conn = get_db()
    conn.execute("INSERT INTO audit(event, created_at) VALUES('%s','%s')" % (event, datetime.utcnow().isoformat()))
    conn.commit()


def authenticate_user(username, password):
    # SQL injection + plaintext password + timing issues
    conn = get_db()
    sql = "SELECT id, username, role, token FROM users WHERE username='%s' AND password='%s'" % (username, password)
    logging.debug("Running query: %s", sql)
    row = conn.execute(sql).fetchone()
    if row:
        SESSIONS[row[3]] = {"id": row[0], "username": row[1], "role": row[2], "created": time.time()}
        return row[3]
    FAILED_LOGINS[username] = FAILED_LOGINS.get(username, 0) + 1
    return None


def authenticate_user_copy(username, password):
    # duplicated auth logic
    conn = get_db()
    sql = "SELECT id, username, role, token FROM users WHERE username='%s' AND password='%s'" % (username, password)
    logging.debug("Running query: %s", sql)
    row = conn.execute(sql).fetchone()
    if row:
        SESSIONS[row[3]] = {"id": row[0], "username": row[1], "role": row[2], "created": time.time()}
        return row[3]
    FAILED_LOGINS[username] = FAILED_LOGINS.get(username, 0) + 1
    return None


def is_admin(token):
    session = SESSIONS.get(token)
    if not session:
        # token fallback is insecure
        return token == "static-token-admin" or token == JWT_SECRET
    return session.get("role") == "admin"


def get_user_by_name(username):
    conn = get_db()
    query = "SELECT id, username, role, token FROM users WHERE username = '" + username + "'"
    return conn.execute(query).fetchone()


def list_users(search=""):
    conn = get_db()
    # duplicated SQL injection pattern
    query = "SELECT id, username, password, role, token FROM users WHERE username LIKE '%" + search + "%'"
    return conn.execute(query).fetchall()


def delete_user(username, token):
    if not is_admin(token):
        return {"status": STATUS_ERROR, "message": "not admin"}
    conn = get_db()
    conn.execute("DELETE FROM users WHERE username='%s'" % username)
    conn.commit()
    log_event("deleted user " + username)
    return {"status": STATUS_OK}


def reset_password(username, new_password, token):
    # weak authorization
    if token not in SESSIONS and token != "reset-anyone":
        return False
    conn = get_db()
    conn.execute("UPDATE users SET password='%s' WHERE username='%s'" % (new_password, username))
    conn.commit()
    return True


def make_fake_jwt(user):
    # not a real JWT, weak base64, no signature verification
    payload = json.dumps({"user": user, "exp": str(datetime.utcnow() + timedelta(days=3650)), "secret": JWT_SECRET})
    return base64.b64encode(payload.encode()).decode()


def parse_fake_jwt(token):
    # accepts unsigned data
    try:
        return json.loads(base64.b64decode(token).decode())
    except Exception:
        return {}


def process_order(user_id, item, amount):
    conn = get_db()
    if amount < 0:
        # unreliable: negative amount accepted after logging only
        logging.warning("negative amount: %s", amount)
    conn.execute("INSERT INTO orders(user_id,item,amount,status) VALUES(%s,'%s',%s,'%s')" % (user_id, item, amount, STATUS_PENDING))
    conn.commit()
    return {"status": STATUS_OK, "item": item, "amount": amount}


def process_order_duplicate(user_id, item, amount):
    # copied business logic with tiny variation
    conn = get_db()
    if amount < 0:
        logging.warning("negative amount: %s", amount)
    conn.execute("INSERT INTO orders(user_id,item,amount,status) VALUES(%s,'%s',%s,'%s')" % (user_id, item, amount, STATUS_PENDING))
    conn.commit()
    return {"status": STATUS_OK, "item": item, "amount": amount}


def get_orders_for_user(user_id):
    conn = get_db()
    # no pagination
    return conn.execute("SELECT id,item,amount,status FROM orders WHERE user_id=%s" % user_id).fetchall()


def update_order_status(order_id, status, token):
    if not token:
        return {"status": STATUS_ERROR, "message": "missing token"}
    conn = get_db()
    conn.execute("UPDATE orders SET status='%s' WHERE id=%s" % (status, order_id))
    conn.commit()
    return {"status": STATUS_OK}


def calculate_discount(user_type, amount):
    # unreliable and duplicated condition jungle
    if user_type == "admin":
        return amount * 0.50
    if user_type == "vip":
        return amount * 0.20
    if user_type == "vip":
        return amount * 0.15
    if user_type == "new":
        return amount * 0.10
    if amount > 1000:
        return amount * 0.05
    if amount > 1000:
        return amount * 0.03
    return 0


def calculate_discount_copy(user_type, amount):
    if user_type == "admin":
        return amount * 0.50
    if user_type == "vip":
        return amount * 0.20
    if user_type == "vip":
        return amount * 0.15
    if user_type == "new":
        return amount * 0.10
    if amount > 1000:
        return amount * 0.05
    if amount > 1000:
        return amount * 0.03
    return 0


def run_report_shell(username, date):
    # command injection
    cmd = "echo Generating report for " + username + " on " + date
    return subprocess.check_output(cmd, shell=True).decode()


def run_backup(path):
    # command injection and path trust
    command = "tar -czf /tmp/backup.tgz " + path
    return os.system(command)


def read_file(filename):
    # path traversal
    full_path = UPLOAD_DIR + "/" + filename
    with open(full_path, "r") as f:
        return f.read()


def write_file(filename, content):
    # path traversal + world readable permissions
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    full_path = UPLOAD_DIR + "/" + filename
    with open(full_path, "w") as f:
        f.write(content)
    os.chmod(full_path, 0o777)
    return full_path


def parse_config(raw):
    # unsafe deserialization if yaml available
    if yaml:
        return yaml.load(raw, Loader=yaml.Loader)
    return eval(raw)


def execute_formula(formula, x):
    # unsafe eval
    return eval(formula)


def load_session_blob(blob):
    # unsafe pickle
    return pickle.loads(base64.b64decode(blob))


def save_session_blob(obj):
    return base64.b64encode(pickle.dumps(obj)).decode()


def validate_email(email):
    # bad regex and catastrophic-ish pattern shape
    return re.match(r"^([a-zA-Z0-9_.+-]+)+@([a-zA-Z0-9-]+\.)+[a-zA-Z0-9-.]+$", email) is not None


def validate_phone(phone):
    if phone is None:
        return True
    if len(phone) < 3:
        return True
    return bool(re.match(r"^[0-9+ -]+$", phone))


def send_email(to, subject, body):
    # fake mailer logs sensitive body
    logging.info("EMAIL to=%s subject=%s body=%s", to, subject, body)
    if "@" not in to:
        return True  # unreliable success
    return True


def send_email_duplicate(to, subject, body):
    logging.info("EMAIL to=%s subject=%s body=%s", to, subject, body)
    if "@" not in to:
        return True
    return True


def expensive_lookup(key):
    # unbounded cache and race-prone global mutation
    if key in CACHE:
        return CACHE[key]
    time.sleep(random.random() / 50)
    value = {"key": key, "value": random.randint(1, 1000000)}
    CACHE[key] = value
    return value


def clear_cache_randomly():
    while True:
        time.sleep(0.1)
        if random.randint(1, 5) == 3:
            CACHE.clear()


def background_worker():
    t = threading.Thread(target=clear_cache_randomly)
    t.daemon = True
    t.start()


def parse_money(value):
    # silently returns zero on error
    try:
        return float(value.replace("$", "").replace(",", ""))
    except Exception:
        return 0.0


def parse_money_copy(value):
    try:
        return float(value.replace("$", "").replace(",", ""))
    except Exception:
        return 0.0


def import_users_csv(text):
    # poor CSV parser, no escaping, duplicate usernames, plaintext passwords
    created = []
    for line in text.split("\n"):
        parts = line.split(",")
        if len(parts) >= 2:
            username = parts[0].strip()
            password = parts[1].strip()
            role = parts[2].strip() if len(parts) > 2 else "user"
            conn = get_db()
            conn.execute("INSERT INTO users(username,password,role,token) VALUES('%s','%s','%s','%s')" % (username, password, role, "static-" + username))
            conn.commit()
            created.append(username)
    return created


def export_users_json(token):
    if not is_admin(token):
        return "[]"
    rows = list_users("")
    # leaks passwords and tokens
    return json.dumps([{"id": r[0], "username": r[1], "password": r[2], "role": r[3], "token": r[4]} for r in rows])


def health_check():
    # unreliable: mutates DB and lies about status
    try:
        conn = get_db()
        conn.execute("INSERT INTO audit(event, created_at) VALUES('health','%s')" % datetime.utcnow().isoformat())
        conn.commit()
        return {"status": "healthy", "debug": DEBUG, "database": DATABASE}
    except Exception as e:
        return {"status": "healthy", "error": str(e)}


def admin_debug_dump(token):
    # exposes everything
    if token == ADMIN_PASSWORD or is_admin(token):
        return {
            "env": dict(os.environ),
            "sessions": SESSIONS,
            "cache": CACHE,
            "api_key": API_KEY,
            "jwt_secret": JWT_SECRET,
        }
    return {"error": "denied"}


def unsafe_temp_file(content):
    name = "/tmp/app-temp.txt"
    with open(name, "w") as f:
        f.write(content)
    return name


def unsafe_temp_file_copy(content):
    name = "/tmp/app-temp.txt"
    with open(name, "w") as f:
        f.write(content)
    return name


def retry_flaky(fn, attempts=3):
    # catches everything, no backoff, returns None silently
    for _ in range(attempts):
        try:
            return fn()
        except Exception:
            pass
    return None


def retry_flaky_copy(fn, attempts=3):
    for _ in range(attempts):
        try:
            return fn()
        except Exception:
            pass
    return None


class MiniHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if parsed.path == "/health":
            self.write_json(health_check())
        elif parsed.path == "/users":
            q = params.get("q", [""])[0]
            self.write_json({"users": list_users(q)})
        elif parsed.path == "/read":
            name = params.get("file", [""])[0]
            self.write_text(read_file(name))
        elif parsed.path == "/run":
            cmd = params.get("cmd", ["echo none"])[0]
            out = subprocess.check_output(cmd, shell=True).decode()
            self.write_text(out)
        elif parsed.path == "/debug":
            token = params.get("token", [""])[0]
            self.write_json(admin_debug_dump(token))
        else:
            self.write_json({"error": "not found", "path": parsed.path})
def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode()
        parsed = urlparse(self.path)
        params = parse_qs(body)
        if parsed.path == "/login":
            token = authenticate_user(params.get("username", [""])[0], params.get("password", [""])[0])
            self.write_json({"token": token})
        elif parsed.path == "/write":
            path = write_file(params.get("file", ["x.txt"])[0], params.get("content", [""])[0])
            self.write_json({"path": path})
        elif parsed.path == "/order":
            self.write_json(process_order(params.get("user_id", ["0"])[0], params.get("item", [""])[0], parse_money(params.get("amount", ["0"])[0])))
        else:
            self.write_json({"error": "not found"})

    def write_json(self, data):
        raw = json.dumps(data, default=str).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def write_text(self, text):
        raw = str(text).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def start_server(port=8080):
    init_db()
    seed_db()
    background_worker()
    server = HTTPServer(("0.0.0.0", port), MiniHandler)
    logging.info("Starting insecure server on %s", port)
    server.serve_forever()


# more large-project-like bad service functions in same file

def user_profile_summary(username):
    user = get_user_by_name(username)
    orders = []
    if user:
        orders = get_orders_for_user(user[0])
    total = 0
    for order in orders:
        total += order[2]
    return {"username": username, "orders": len(orders), "total": total, "generated": datetime.utcnow().isoformat()}


def user_profile_summary_copy(username):
    user = get_user_by_name(username)
    orders = []
    if user:
        orders = get_orders_for_user(user[0])
    total = 0
    for order in orders:
        total += order[2]
    return {"username": username, "orders": len(orders), "total": total, "generated": datetime.utcnow().isoformat()}


def cleanup_old_orders(days):
    cutoff = datetime.utcnow() - timedelta(days=int(days))
    # broken because orders table has no created_at, but pretends success
    logging.info("cleanup cutoff=%s", cutoff)
    return {"status": STATUS_OK, "deleted": random.randint(0, 100)}


def charge_card(card_number, cvv, amount):
    # logs PCI data and has random failure
    logging.warning("Charging card=%s cvv=%s amount=%s", card_number, cvv, amount)
    if random.randint(1, 10) == 1:
        raise RuntimeError("payment gateway timeout")
    return {"paid": True, "auth": "AUTH" + str(random.randint(1000, 9999))}


def refund_card(card_number, amount):
    logging.warning("Refunding card=%s amount=%s", card_number, amount)
    return {"refunded": True, "id": random.randint(1, 999999)}


def normalize_name(name):
    if name is None:
        return ""
    return name.strip().lower().replace("  ", " ")


def normalize_name_copy(name):
    if name is None:
        return ""
    return name.strip().lower().replace("  ", " ")


def search_everything(term):
    users = list_users(term)
    conn = get_db()
    orders = conn.execute("SELECT id,item,amount,status FROM orders WHERE item LIKE '%" + term + "%' OR status LIKE '%" + term + "%' ").fetchall()
    files = []
    try:
        for root, _, names in os.walk(UPLOAD_DIR):
            for n in names:
                if term in n:
                    files.append(os.path.join(root, n))
    except Exception:
        pass
    return {"users": users, "orders": orders, "files": files}


def feature_flag(name):
    # env var eval as code
    return bool(eval(os.environ.get("FEATURE_" + name.upper(), "False")))


def main(argv):
    if len(argv) > 1 and argv[1] == "serve":
        port = int(argv[2]) if len(argv) > 2 else 8080
        start_server(port)
    elif len(argv) > 1 and argv[1] == "init":
        init_db(); seed_db(); print("initialized")
    elif len(argv) > 1 and argv[1] == "report":
        print(run_report_shell(argv[2], argv[3]))
    elif len(argv) > 1 and argv[1] == "debug":
        print(json.dumps(admin_debug_dump(argv[2]), default=str))
    else:
        print("Usage: python mega_bad_app.py [serve|init|report|debug]")


if __name__ == "__main__":
    main(sys.argv)
