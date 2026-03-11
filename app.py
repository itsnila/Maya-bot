import os
import time
import random
import threading
import requests
import logging
import json
import mysql.connector
from flask import Flask, request

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ================================================================
# CONFIGURATION (Render Environment Variables)
# ================================================================
PAGE_ACCESS_TOKEN = "EAAMjx3bzyhkBQ02pgVXsCdSKsNZBXegi2nWyV2B05kTZAiPKgaZBZCU0pmrs05YNdhFGo47QKFuehDJ6NiZAlQ14Cc3Ipi8hym97EdE56Mf3l3WMWmZB8WgAzsrISeFEZBIKLcgYsvsERNg9F2nr6QXzdkwgOgyubj03u0uw3XNNOeOhOSVGIHgxxAgWtBT026yEZAJlNPtr"
VERIFY_TOKEN = "MAYA_VERIFY_TOKEN"

# আপনার সিরিয়াল অনুযায়ী কী-গুলো নেওয়া হচ্ছে
GEMINI_KEY = os.environ.get("GEMINI_KEY_1")
GROQ_KEY = os.environ.get("GROQ_KEY_1")
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY_1")

# ডাটাবেজ কনফিগারেশন
DB_CONFIG = {
    'host': '161.248.189.34',
    'user': 'nogorde1_maya',
    'password': 'gmsbd1122@@',
    'database': 'nogorde1_maya',
    'port': 3306,
    'connect_timeout': 20
}

# ================================================================
# AI ENGINE (Smart Fallback: Gemini -> Groq -> OpenRouter)
# ================================================================
def get_maya_reply(prompt, history):
    system_prompt = "তোমার নাম মায়া। তুমি ইউজারের প্রেমিকা। খুব মিষ্টি ও রোমান্টিক মেয়ে। ছোট ছোট উত্তর দাও।"
    
    messages = [{"role": "system", "content": system_prompt}]
    for chat in history:
        messages.append(chat)
    messages.append({"role": "user", "content": prompt})

    # --- ১. প্রথমে Gemini ট্রাই করবে ---
    if GEMINI_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_KEY}"
            payload = {"contents": [{"parts": [{"text": f"{system_prompt}\n\nUser: {prompt}"}]}]}
            response = requests.post(url, json=payload, timeout=10)
            res_data = response.json()
            if 'candidates' in res_data:
                return res_data['candidates'][0]['content']['parts'][0]['text']
        except Exception as e:
            logger.error(f"Gemini failed: {e}")

    # --- ২. Gemini কাজ না করলে Groq ট্রাই করবে ---
    if GROQ_KEY:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
            payload = {"model": "llama3-8b-8192", "messages": messages, "temperature": 0.8}
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            res_data = response.json()
            if 'choices' in res_data:
                return res_data['choices'][0]['message']['content']
        except Exception as e:
            logger.error(f"Groq failed: {e}")

    # --- ৩. Groq কাজ না করলে OpenRouter ট্রাই করবে ---
    if OPENROUTER_KEY:
        try:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {OPENROUTER_KEY.strip()}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://nogordeal.com"
            }
            payload = {"model": "google/gemini-flash-1.5-8b", "messages": messages}
            response = requests.post(url, json=payload, headers=headers, timeout=12)
            res_data = response.json()
            if 'choices' in res_data:
                return res_data['choices'][0]['message']['content']
        except Exception as e:
            logger.error(f"OpenRouter failed: {e}")

    return "সোনা, আমার সার্ভারে একটু সমস্যা হচ্ছে। একটু পর আবার বলবে?"

# ================================================================
# DATABASE & MESSAGING FUNCTIONS
# ================================================================
def get_db_conn():
    return mysql.connector.connect(**DB_CONFIG)

def get_user_data(sender_id):
    try:
        conn = get_db_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE sender_id = %s", (sender_id,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user:
            user['history'] = json.loads(user['history']) if user['history'] else []
            return user
        return {"sender_id": sender_id, "name": None, "history": [], "last_seen": int(time.time())}
    except Exception as e:
        logger.error(f"DB Read Error: {e}")
        return {"sender_id": sender_id, "name": None, "history": [], "last_seen": int(time.time())}

def save_user_data(sender_id, name, history):
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        now = int(time.time())
        history_json = json.dumps(history)
        query = """INSERT INTO users (sender_id, name, history, last_seen) VALUES (%s, %s, %s, %s) 
                   ON DUPLICATE KEY UPDATE name=%s, history=%s, last_seen=%s"""
        cursor.execute(query, (sender_id, name, history_json, now, name, history_json, now))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"DB Save Error: {e}")

def send_text(sender_id, text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    requests.post(url, json={"recipient": {"id": sender_id}, "message": {"text": text}})

# ================================================================
# WEBHOOK & HANDLERS
# ================================================================
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        return "Failed", 403
    
    data = request.json
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                if "message" in event and "text" in event["message"]:
                    threading.Thread(target=process_maya, args=(event["sender"]["id"], event["message"]["text"])).start()
    return "OK", 200

def process_maya(sender_id, text):
    user = get_user_data(sender_id)
    reply = get_maya_reply(text, user['history'])
    send_text(sender_id, reply)
    
    user['history'].append({"role": "user", "content": text})
    user['history'].append({"role": "assistant", "content": reply})
    save_user_data(sender_id, user['name'], user['history'][-10:])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
