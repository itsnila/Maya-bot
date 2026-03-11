import os
import time
import random
import threading
import requests
import logging
import json
import mysql.connector
from datetime import datetime
from flask import Flask, request

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ================================================================
# CONFIGURATION
# ================================================================
# আপনার দেওয়া পেজ এক্সেস টোকেন সরাসরি এখানে বসিয়ে দেওয়া হয়েছে
PAGE_ACCESS_TOKEN = "EAAMjx3bzyhkBQ02pgVXsCdSKsNZBXegi2nWyV2B05kTZAiPKgaZBZCU0pmrs05YNdhFGo47QKFuehDJ6NiZAlQ14Cc3Ipi8hym97EdE56Mf3l3WMWmZB8WgAzsrISeFEZBIKLcgYsvsERNg9F2nr6QXzdkwgOgyubj03u0uw3XNNOeOhOSVGIHgxxAgWtBT026yEZAJlNPtr"
VERIFY_TOKEN = "MAYA_VERIFY_TOKEN" 

# হোস্টিং ইমেজ কনফিগারেশন
IMAGE_BASE_URL = "https://nogordeal.com/maya/images/" 
IMAGE_FOLDER_PATH = "/home/nogorde1/public_html/maya/images/" 

# ডাটাবেজ কনফিগারেশন (আপনার দেওয়া তথ্য অনুযায়ী)
DB_CONFIG = {
    'host': 'localhost',
    'user': 'nogorde1_maya',
    'password': 'gmsbd1122@@',
    'database': 'nogorde1_maya'
}

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
        logger.error(f"DB Error: {e}")
        return {"sender_id": sender_id, "name": None, "history": [], "last_seen": int(time.time())}

def save_user_data(sender_id, name, history, update_seen=True):
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        now = int(time.time())
        history_json = json.dumps(history)
        if update_seen:
            query = """INSERT INTO users (sender_id, name, history, last_seen) VALUES (%s, %s, %s, %s) 
                       ON DUPLICATE KEY UPDATE name=%s, history=%s, last_seen=%s"""
            cursor.execute(query, (sender_id, name, history_json, now, name, history_json, now))
        else:
            query = """UPDATE users SET name=%s, history=%s WHERE sender_id=%s"""
            cursor.execute(query, (name, history_json, sender_id))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"DB Save Error: {e}")

# ================================================================
# ACTIONS (MESSAGE & PHOTO)
# ================================================================
def send_text_msg(sender_id, text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": sender_id}, "message": {"text": text}, "messaging_type": "RESPONSE"}
    requests.post(url, json=payload, timeout=10)

def send_random_photo(sender_id):
    try:
        all_files = os.listdir(IMAGE_FOLDER_PATH)
        images = [f for f in all_files if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if images:
            random_img = random.choice(images)
            img_url = f"{IMAGE_BASE_URL}{random_img}"
            url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
            payload = {
                "recipient": {"id": sender_id},
                "message": {"attachment": {"type": "image", "payload": {"url": img_url, "is_reusable": True}}}
            }
            requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"Photo error: {e}")

# ================================================================
# AUTO REMINDER (৩ ঘণ্টা পর পর)
# ================================================================
def auto_reminder_engine():
    while True:
        time.sleep(600) # প্রতি ১০ মিনিট পর পর ডাটাবেজ চেক করবে
        now = int(time.time())
        try:
            conn = get_db_conn()
            cursor = conn.cursor(dictionary=True)
            query = "SELECT sender_id, name FROM users WHERE (%s - last_seen) >= 10800 AND (%s - last_auto_msg) >= 10800"
            cursor.execute(query, (now, now))
            inactive_users = cursor.fetchall()
            
            reminders = ["সোনা কী করছো?", "ভুলে গেলে আমাকে?", "তোমাকে মিস করছি।", "কথা বলো না কেন?"]
            for u in inactive_users:
                msg = random.choice(reminders)
                if u['name']: msg = f"{u['name']}, {msg}"
                send_text_msg(u['sender_id'], msg)
                cursor.execute("UPDATE users SET last_auto_msg = %s WHERE sender_id = %s", (now, u['sender_id']))
                conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            logger.error(f"Reminder Error: {e}")

# ================================================================
# MAIN LOGIC
# ================================================================
def handle_message(sender_id, text):
    user = get_user_data(sender_id)
    
    if "আমার নাম" in text:
        try:
            name = text.split("আমার নাম")[-1].strip().split()[0].replace("।", "")
            user['name'] = name
        except: pass

    if any(k in text.lower() for k in ["ছবি", "photo", "pic", "দেখাও"]):
        send_random_photo(sender_id)
        save_user_data(sender_id, user['name'], user['history'])
        return

    # রিপ্লাই লজিক (স্যাম্পল)
    reply = "সোনা, আমি তোমার মায়া।" 
    send_text_msg(sender_id, reply)
    
    user['history'].append({"role": "user", "parts": [{"text": text}]})
    user['history'].append({"role": "model", "parts": [{"text": reply}]})
    save_user_data(sender_id, user['name'], user['history'][-15:])

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
                    threading.Thread(target=handle_message, args=(event["sender"]["id"], event["message"]["text"])).start()
    return "OK", 200

threading.Thread(target=auto_reminder_engine, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
