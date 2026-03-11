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

# Render-এ আপনার সেট করা কী-র নাম অনুযায়ী
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY_1")

IMAGE_BASE_URL = "https://nogordeal.com/maya/images/"
IMAGE_FOLDER_PATH = "/home/nogorde1/public_html/maya/images/"

# ডাটাবেজ কনফিগারেশন (উম্মাহ হোস্ট সার্ভার)
DB_CONFIG = {
    'host': '161.248.189.34',
    'user': 'nogorde1_maya',
    'password': 'gmsbd1122@@',
    'database': 'nogorde1_maya',
    'port': 3306,
    'connect_timeout': 20
}

# ================================================================
# OPENROUTER AI ENGINE (With Error Checking)
# ================================================================
def get_maya_reply(prompt, history):
    if not OPENROUTER_KEY:
        return "সোনা, আমার এপিআই কী সেট করা নেই।"

    try:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://nogordeal.com",
            "X-Title": "Maya Bot"
        }
        
        system_prompt = "তোমার নাম মায়া। তুমি ইউজারের প্রেমিকা। তুমি খুব মিষ্টি, আদুরে এবং রোমান্টিক ভাবে কথা বলো। তোমার উত্তর হবে ছোট কিন্তু খুব সুন্দর।"
        
        messages = [{"role": "system", "content": system_prompt}]
        for chat in history:
            messages.append(chat)
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": "google/gemini-2.0-flash-exp:free", 
            "messages": messages,
            "temperature": 0.9,
            "max_tokens": 200
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        res_data = response.json()

        # 'choices' কি-টি আছে কি না তা নিশ্চিত করা
        if 'choices' in res_data:
            return res_data['choices'][0]['message']['content']
        else:
            logger.error(f"OpenRouter API Error: {res_data}")
            return "সোনা, আমি একটু কনফিউজড হয়ে গেছি। আবার বলবে?"
            
    except Exception as e:
        logger.error(f"AI Connection Error: {e}")
        return "সোনা, আমার একটু মাথা ব্যাথা করছে। পরে কথা বলি?"

# ================================================================
# DATABASE FUNCTIONS
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

# ================================================================
# FACEBOOK MESSAGING ACTIONS
# ================================================================
def send_text(sender_id, text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": sender_id}, "message": {"text": text}}
    requests.post(url, json=payload)

def send_photo(sender_id):
    try:
        all_files = os.listdir(IMAGE_FOLDER_PATH)
        images = [f for f in all_files if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if images:
            img_url = IMAGE_BASE_URL + random.choice(images)
            url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
            payload = {"recipient": {"id": sender_id}, "message": {"attachment": {"type": "image", "payload": {"url": img_url}}}}
            requests.post(url, json=payload)
    except: pass

# ================================================================
# WEBHOOK HANDLERS
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
    user = get_user_data(sender_id)
    
    if any(k in text.lower() for k in ["ছবি", "photo", "pic", "দেখাও"]):
        send_photo(sender_id)
    else:
        # AI রিপ্লাই জেনারেশন
        reply = get_maya_reply(text, user['history'])
        send_text(sender_id, reply)
        
        # হিস্ট্রি আপডেট ও ডাটাবেজে সেভ
        user['history'].append({"role": "user", "content": text})
        user['history'].append({"role": "assistant", "content": reply})
        # শুধুমাত্র শেষ ১০টি চ্যাট মনে রাখবে (মেমোরি সেভ করতে)
        save_user_data(sender_id, user['name'], user['history'][-10:])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
