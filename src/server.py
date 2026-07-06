import os
import sys
import random
import logging
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, session
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Ensure project root is in system path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.config as config
import src.database.local_db as local_db
from src.main import ValidationOrchestrator

logger = logging.getLogger("validation_tool")

app = Flask(__name__)
# Cryptographically sign cookies for Flask session security
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "planning-secret-validation-key-poc-2026")

# Initialize DB on load
local_db.init_db()

# Lazy loaded orchestrator instance
_orchestrator = None

def get_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ValidationOrchestrator(dry_run=False)
    return _orchestrator

def send_otp_email(to_email, code):
    smtp_server = os.environ.get("SMTP_SERVER")
    smtp_port = os.environ.get("SMTP_PORT", "587")
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASSWORD")
    
    # Check if SMTP parameters are set
    if not smtp_server or not smtp_user or not smtp_pass:
        logger.warning(f"SMTP not configured. OTP for {to_email} is: {code} (Saved to data/otp_debug.log)")
        # Debug file fallback for local testing
        debug_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "otp_debug.log")
        os.makedirs(os.path.dirname(debug_path), exist_ok=True)
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(f"EMAIL: {to_email}\nOTP: {code}\nDATETIME: {datetime.utcnow().isoformat()}\n")
        return False
        
    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = to_email
        msg['Subject'] = "Código de Confirmação - Validador ClickUp-BQ"
        
        body = f"""Olá,
        
Você solicitou acesso ao Painel de Controle de Validação ClickUp-BQ da Planning.
Seu código de confirmação de dose única (OTP) é:

👉 CODE: {code}

Este código expira em 10 minutos. Se você não solicitou este acesso, por favor ignore este e-mail.

--
Building your company's future. Today.
Planning - Equipe clickup
"""
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        server = smtplib.SMTP(smtp_server, int(smtp_port))
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, to_email, msg.as_string())
        server.quit()
        logger.info(f"OTP email sent successfully to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP email to {to_email}: {e}")
        # Always save to debug log as a fallback so testing doesn't block
        debug_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "otp_debug.log")
        os.makedirs(os.path.dirname(debug_path), exist_ok=True)
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(f"EMAIL: {to_email}\nOTP: {code}\nDATETIME: {datetime.utcnow().isoformat()}\nERROR: {e}\n")
        return False

# Decorator to secure API routes
def require_login(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({"error": "Unauthorized. Login required."}), 401
        
        # Additional safety check that the email is still active in SQLite
        email = session['user']
        if not local_db.check_user_active(email):
            session.pop('user', None)
            return jsonify({"error": "User account is inactive or deleted."}), 403
            
        return f(*args, **kwargs)
    return decorated_function

# --- STATIC FILES PATHS ---
PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")

@app.route("/")
def serve_index():
    return send_from_directory(PUBLIC_DIR, "index.html")

@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory(PUBLIC_DIR, path)

# --- WEBHOOK VALIDATE GATEWAY (NO AUTH FOR INTEGRATION TRIGGER) ---
@app.route("/validate", methods=["POST"])
def validate_task_webhook():
    # 1. Check if engine is active globally
    if not local_db.is_motor_ativo():
        logger.warning("Webhook /validate blocked because engine is PAUSED")
        return jsonify({"error": "Validation engine is paused/disabled by the administrator.", "status": "paused"}), 503

    data = request.get_json() or {}
    task_id = data.get("task_id")
    dry_run = data.get("dry_run", False)
    
    if not task_id:
        return jsonify({"error": "Missing task_id"}), 400
        
    logger.info(f"Received webhook request for task {task_id}")
    try:
        orch = get_orchestrator()
        task = orch.clickup_client._request("GET", f"task/{task_id}")
        
        # Check task status and ensure it's ONLY processed if it belongs to 'para começar'
        status_name = task.get("status", {}).get("status", "").lower()
        if status_name != "para começar" and status_name != "para comecar":
            logger.info(f"Skipping task {task_id} since its status '{status_name}' is not 'para começar'")
            return jsonify({"message": f"Task skipped. Status '{status_name}' is not 'para começar'."}), 200

        success = orch.validate_single_task(task)
        return jsonify({
            "success": success, 
            "task_id": task_id, 
            "status": "validated"
        })
    except Exception as e:
        logger.error(f"Error handling webhook task validation: {e}")
        return jsonify({"error": str(e)}), 500

# --- AUTH API ---
@app.route("/api/auth/request-otp", methods=["POST"])
def request_otp():
    data = request.get_json() or {}
    email = data.get("email", "").lower().strip()
    
    if not email:
        return jsonify({"error": "E-mail obrigatório"}), 400
        
    if not email.endswith("@planning.com.br"):
        return jsonify({"error": "Apenas e-mails corporativos @planning.com.br são permitidos."}), 400
        
    # Check if user is registered/active
    # If users table is empty, allow the first admin user to log in and bootstrap
    users = local_db.list_users()
    if not users and email == "alex.biudes@planning.com.br":
        local_db.add_user(email)
        
    if not local_db.check_user_active(email):
        return jsonify({"error": "Acesso não autorizado para este e-mail. Peça um convite a um administrador."}), 403
        
    # Generate 6-digit OTP
    code = f"{random.randint(100000, 999999)}"
    local_db.save_otp_code(email, code)
    
    # Send email or log code
    email_sent = send_otp_email(email, code)
    
    return jsonify({
        "message": "Código enviado por e-mail." if email_sent else "Código gerado no console do servidor (Modo Homologação).",
        "email": email,
        "debug_mode": not email_sent
    })

@app.route("/api/auth/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json() or {}
    email = data.get("email", "").lower().strip()
    code = data.get("code", "").strip()
    
    if not email or not code:
        return jsonify({"error": "E-mail e código são obrigatórios"}), 400
        
    if local_db.verify_otp_code(email, code):
        session['user'] = email
        return jsonify({"success": True, "user": email, "message": "Autenticado com sucesso"})
    else:
        return jsonify({"error": "Código inválido ou expirado."}), 400

@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.pop('user', None)
    return jsonify({"success": True, "message": "Sessão encerrada"})

@app.route("/api/auth/me", methods=["GET"])
def check_me():
    if 'user' in session:
        email = session['user']
        if local_db.check_user_active(email):
            return jsonify({"authenticated": True, "user": email})
    return jsonify({"authenticated": False})

# --- CONTROL API (PROTECTED) ---
@app.route("/api/status", methods=["GET"])
@require_login
def get_status():
    return jsonify({
        "motor_ativo": local_db.is_motor_ativo(),
        "stats": local_db.get_stats(),
        "project_name": config.PROJECT_NAME,
        "version": "2.2.0"
    })

@app.route("/api/toggle", methods=["POST"])
@require_login
def toggle_motor():
    data = request.get_json() or {}
    state = data.get("motor_ativo")
    if state is None:
        return jsonify({"error": "Missing 'motor_ativo' parameter"}), 400
        
    local_db.set_motor_state(bool(state))
    return jsonify({"success": True, "motor_ativo": local_db.is_motor_ativo()})

@app.route("/api/history", methods=["GET"])
@require_login
def get_history():
    logs = local_db.get_recent_logs(limit=20)
    return jsonify({"logs": logs})

# --- USER MANAGEMENT API (PROTECTED) ---
@app.route("/api/users", methods=["GET"])
@require_login
def get_users():
    return jsonify({"users": local_db.list_users()})

@app.route("/api/users/invite", methods=["POST"])
@require_login
def invite_user():
    data = request.get_json() or {}
    email = data.get("email", "").lower().strip()
    
    if not email:
        return jsonify({"error": "E-mail é obrigatório"}), 400
        
    if not email.endswith("@planning.com.br"):
        return jsonify({"error": "Apenas e-mails corporativos @planning.com.br são permitidos."}), 400
        
    success = local_db.add_user(email)
    if success:
        return jsonify({"success": True, "message": f"Usuário {email} convidado com sucesso!"})
    else:
        return jsonify({"error": "Usuário já existe na lista ou ocorreu um erro."}), 409

@app.route("/api/users/remove", methods=["POST"])
@require_login
def remove_user():
    data = request.get_json() or {}
    email = data.get("email", "").lower().strip()
    
    if not email:
        return jsonify({"error": "E-mail é obrigatório"}), 400
        
    success = local_db.remove_user(email)
    if success:
        return jsonify({"success": True, "message": f"Acesso de {email} revogado com sucesso."})
    else:
        return jsonify({"error": "Não é possível remover o administrador principal ou usuário não encontrado."}), 400

# --- FORCED MANUAL RUN (PROTECTED) ---
@app.route("/api/force-validate", methods=["POST"])
@require_login
def force_validate():
    data = request.get_json() or {}
    task_id = data.get("task_id")
    if not task_id:
        return jsonify({"error": "Missing task_id"}), 400
        
    try:
        orch = get_orchestrator()
        task = orch.clickup_client._request("GET", f"task/{task_id}")
        success = orch.validate_single_task(task)
        return jsonify({"success": True, "validated_success": success})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Starting Flask Admin & API server on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)
