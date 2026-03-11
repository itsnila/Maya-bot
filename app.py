import os
import time
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
# CONFIGURATION
# ================================================================
PAGE_ACCESS_TOKEN = "EAAMjx3bzyhkBQ02pgVXsCdSKsNZBXegi2nWyV2B05kTZAiPKgaZBZCU0pmrs05YNdhFGo47QKFuehDJ6NiZAlQ14Cc3Ipi8hym97EdE56Mf3l3WMWmZB8WgAzsrISeFEZBIKLcgYsvsERNg9F2nr6QXzdkwgOgyubj03u0uw3XNNOeOhOSVGIHgxxAgWtBT026yEZAJlNPtr"
VERIFY_TOKEN = "MAYA_VERIFY_TOKEN"

# API Keys from Render Environment Variables
GEMINI_KEY = os.environ.get("GEMINI_KEY_1")
GROQ_KEY = os.environ.get("GROQ_KEY_1")
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY_1")

# Database Config - local থেকে সরিয়ে remote IP দেওয়া হয়েছে
DB_CONFIG = {
    'host': '161.248.189.34',
    'user': 'nogorde1_maya',
    'password': 'gmsbd1122@@',
    'database': 'nogorde1_maya',
    'port': 3306,
    'connect_timeout': 30
}

# ================================================================
# AI ENGINE (Gemini -> Groq -> OpenRouter)
# ================================================================
def get_maya_reply(prompt, history):
    system_prompt = "তোমার নাম মায়া। তুমি ইউজারের প্রেমিকা। মিষ্টি ও রোমান্টিক ভাবে ছোট উত্তর দাও।"
    
    # --- ১. Gemini (Primary) ---
    if GEMINI_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
            payload = {"contents": [{"parts": [{"text": f"{system_prompt}\nUser: {prompt}"}]}]}
            response = requests.post(url, json=payload, timeout=10)
            res = response.json()
            if 'candidates' in res:
                return res['candidates'][0]['content']['parts'][0]['text']
        except Exception as e: logger.error(f"Gemini Error: {e}")

    # --- ২. Groq (Fallback 1) ---
    if GROQ_KEY:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
            payload = {"model": "llama3-8b-8192", "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]}
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            res = response.json()
            if 'choices' in res:
                return res['choices'][0]['message']['content']
        except Exception as e: logger.error(f"Groq Error: {e}")

    # --- ৩. OpenRouter (Fallback 2) ---
    if OPENROUTER_KEY:
        try:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {"Authorization": f"Bearer {OPENROUTER_KEY.strip()}", "Content-Type": "application/json"}
            payload = {"model": "google/gemini-flash-1.5-8b", "messages": [{"role": "user", "content": prompt}]}
            response = requests.post(url, json=payload, headers=headers, timeout=12)
            res = response.json()
            if 'choices' in res:
                return res['choices'][0]['message']['content']
        except Exception as e: logger.error(f"OpenRouter Error: {e}")

    return "সোনা, আমার নেটওয়ার্কে একটু সমস্যা হচ্ছে। একটু পর আবার বলবে?"

# ================================================================
# DATABASE HANDLERS
# ================================================================
def get_db_conn():
    # 'localhost' এর বদলে রিমোট আইপি ব্যবহার করা হয়েছে এরর ২০০৩ এড়াতে
    return mysql.connector.connect(**DB_CONFIG)

def save_chat(sender_id, user_msg, bot_msg):
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        query = "INSERT INTO chats (sender_id, user_msg, bot_msg) VALUES (%s, %s, %s)"
        cursor.execute(query, (sender_id, user_msg, bot_msg))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e: logger.error(f"DB Save Error: {e}")

# ================================================================
# FACEBOOK WEBHOOK
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
                    threading.Thread(target=process_msg, args=(event["sender"]["id"], event["message"]["text"])).start()
    return "OK", 200

def process_msg(sender_id, text):
    reply = get_maya_reply(text, [])
    send_text(sender_id, reply)
    save_chat(sender_id, text, reply)

def send_text(sender_id, text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    requests.post(url, json={"recipient": {"id": sender_id}, "message": {"text": text}})

# Health Check - Render এর পোর্ট ডিটেকশন ইস্যু সমাধানের জন্য
@app.route("/", methods=["GET"])
def health_check():
    return "Maya Bot is Running", 200

if __name__ == "__main__":
    # Render-এর জন্য সঠিক পোর্ট এবং হোস্ট কনফিগারেশন
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
