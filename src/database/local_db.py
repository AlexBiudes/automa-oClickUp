import os
import sqlite3
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("validation_tool")

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
DB_PATH = os.path.join(DB_DIR, "validator.db")

def get_db_connection():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes SQLite database tables if they do not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Config Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    
    # Insert default config for active status
    cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('motor_ativo', 'true')")
    
    # 2. Audit Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        task_id TEXT,
        uaid TEXT,
        cnpj TEXT,
        empresa TEXT,
        periodo TEXT,
        sucesso INTEGER,
        tempo_ms INTEGER,
        erros_detalhe TEXT
    )
    """)
    
    # 3. Authorized Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        email TEXT PRIMARY KEY,
        is_active INTEGER DEFAULT 1,
        created_at TEXT
    )
    """)
    
    # Insert initial admin user (Alex Biudes)
    cursor.execute("""
    INSERT OR IGNORE INTO users (email, is_active, created_at) 
    VALUES ('alex.biudes@planning.com.br', 1, ?)
    """, (datetime.utcnow().isoformat(),))
    
    # 4. OTP codes Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS otp_codes (
        email TEXT PRIMARY KEY,
        code TEXT,
        expires_at TEXT
    )
    """)
    
    conn.commit()
    conn.close()
    logger.info(f"Local SQLite database initialized at: {DB_PATH}")

def is_motor_ativo() -> bool:
    """Returns True if the validation engine is enabled (motor_ativo = true)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM config WHERE key = 'motor_ativo'")
        row = cursor.fetchone()
        conn.close()
        if row:
            return row["value"].lower() == "true"
        return True
    except Exception as e:
        logger.error(f"Error reading motor_ativo state: {e}")
        return True

def set_motor_state(state: bool):
    """Sets the validation engine state."""
    conn = get_db_connection()
    cursor = conn.cursor()
    val_str = "true" if state else "false"
    cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('motor_ativo', ?)", (val_str,))
    conn.commit()
    conn.close()
    logger.info(f"Engine motor_ativo status set to: {val_str}")

def log_validation_attempt(task_id: str, uaid: str, cnpj: str, empresa: str, periodo: str, sucesso: bool, tempo_ms: int, erros: list):
    """Logs a validation execution in the local SQLite db."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        erros_json = json.dumps(erros, ensure_ascii=False)
        cursor.execute("""
        INSERT INTO audit_logs (timestamp, task_id, uaid, cnpj, empresa, periodo, sucesso, tempo_ms, erros_detalhe)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            task_id,
            uaid,
            cnpj,
            empresa,
            periodo,
            1 if sucesso else 0,
            tempo_ms,
            erros_json
        ))
        conn.commit()
        conn.close()
        logger.info(f"Validation logged in local DB for task {task_id}")
    except Exception as e:
        logger.error(f"Error logging validation in local DB: {e}")

def get_recent_logs(limit=15):
    """Gets the recent validation attempts from SQLite."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    logs = []
    for r in rows:
        logs.append({
            "id": r["id"],
            "timestamp": r["timestamp"],
            "task_id": r["task_id"],
            "uaid": r["uaid"],
            "cnpj": r["cnpj"],
            "empresa": r["empresa"],
            "periodo": r["periodo"],
            "sucesso": bool(r["sucesso"]),
            "tempo_ms": r["tempo_ms"],
            "erros": json.loads(r["erros_detalhe"]) if r["erros_detalhe"] else []
        })
    return logs

def get_stats():
    """Gets metrics for the dashboard KPIs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Processed today
    today_start = datetime.utcnow().strftime("%Y-%m-%d") + "T00:00:00"
    cursor.execute("SELECT COUNT(*) as cnt FROM audit_logs WHERE timestamp >= ?", (today_start,))
    cnt_today = cursor.fetchone()["cnt"]
    
    # Total processed
    cursor.execute("SELECT COUNT(*) as cnt FROM audit_logs")
    cnt_total = cursor.fetchone()["cnt"]
    
    # Success rate
    cursor.execute("SELECT COUNT(*) as cnt FROM audit_logs WHERE sucesso = 1")
    cnt_success = cursor.fetchone()["cnt"]
    success_rate = (cnt_success / cnt_total * 100) if cnt_total > 0 else 100.0
    
    # Avg response time
    cursor.execute("SELECT AVG(tempo_ms) as avg_time FROM audit_logs")
    avg_time = cursor.fetchone()["avg_time"] or 0
    
    conn.close()
    
    return {
        "processed_today": cnt_today,
        "total_processed": cnt_total,
        "success_rate": round(success_rate, 2),
        "avg_time_ms": int(avg_time)
    }

def add_user(email: str) -> bool:
    """Adds a new user if it ends with @planning.com.br."""
    if not email or not email.lower().endswith("@planning.com.br"):
        return False
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (email, is_active, created_at) VALUES (?, 1, ?)", 
                   (email.lower(), datetime.utcnow().isoformat()))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def list_users():
    """Lists all registered users."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT email, is_active, created_at FROM users ORDER BY email")
    rows = cursor.fetchall()
    conn.close()
    return [{"email": r["email"], "is_active": bool(r["is_active"]), "created_at": r["created_at"]} for r in rows]

def remove_user(email: str) -> bool:
    """Deletes a user from the authorized list."""
    # Never delete the initial admin email via UI
    if email.lower() == "alex.biudes@planning.com.br":
        return False
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE email = ?", (email.lower(),))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def check_user_active(email: str) -> bool:
    """Checks if a user is registered and active."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_active FROM users WHERE email = ?", (email.lower(),))
    row = cursor.fetchone()
    conn.close()
    return row is not None and row["is_active"] == 1

def save_otp_code(email: str, code: str):
    """Saves OTP code and sets 10 minutes expiration."""
    expires = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO otp_codes (email, code, expires_at) VALUES (?, ?, ?)", 
                   (email.lower(), code, expires))
    conn.commit()
    conn.close()

def verify_otp_code(email: str, code: str) -> bool:
    """Verifies OTP code and ensures it is not expired."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT code, expires_at FROM otp_codes WHERE email = ?", (email.lower(),))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return False
        
    expires_at = datetime.fromisoformat(row["expires_at"])
    if datetime.utcnow() > expires_at:
        return False
        
    if row["code"] == code:
        # Delete OTP once verified successfully
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM otp_codes WHERE email = ?", (email.lower(),))
        conn.commit()
        conn.close()
        return True
        
    return False
