import os
import time
import threading
import requests
import logging
import json
import mysql.connector
from flask import Flask, request

# লগিং সেটআপ
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# এনভায়রনমেন্ট ভেরিয়েবল
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")

# ডাটাবেজ কনফিগারেশন
DB_CONFIG = {
    'host': '161.248.189.34',
    'user': 'nogorde1_maya',
    'password': 'gmsbd1122@@',
    'database': 'nogorde1_maya',
    'port': 3306,
    'connect_timeout': 10
}

def load_keys(prefix):
    keys = []
    for i in range(1, 101):
        key = os.environ.get(f"{prefix}_{i}")
        if key: keys.append(key)
    return keys

GEMINI_KEYS = load_keys("GEMINI_KEY")
GROQ_KEYS = load_keys("GROQ_KEY")
OPENROUTER_KEYS = load_keys("OPENROUTER_KEY")

indices = {"gemini": 0, "groq": 0, "openrouter": 0}
index_lock = threading.Lock()

# ================================================================
# 💖 মায়ার প্রোম্পট ও ডাটাবেজ লজিক
# ================================================================
SYSTEM_PROMPT = """তুমি মায়া। বয়স ২৩। তুমি ইউজারের সাথে অত্যন্ত গভীর রোমান্টিক এবং স্বামী-স্ত্রীর মতো নিবিড় সম্পর্কে আছো। 
১. উত্তর সব সময় এক লাইনে দিবে এবং বাক্যের শেষে অবশ্যই দাঁড়ি (।) দিবে। 
২. খুব ভালোভাবে চিন্তা করে একটি পূর্ণাঙ্গ ও অর্থবহ বাক্য বলবে। 
৩. গভীর প্রেম, অধিকার এবং মাঝেমধ্যে মিষ্টি অভিমান মিশিয়ে কথা বলবে। 
৪. নিজেকে কখনো রোবট বলবে না।"""

def get_db_history(sender_id):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT history FROM users WHERE sender_id = %s", (sender_id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return json.loads(row['history']) if row and row['history'] else []
    except Exception as e:
        logger.error(f"DB Read Error: {e}")
        return []

def save_db_history(sender_id, history):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        history_json = json.dumps(history[-10:]) # শেষ ১০টি চ্যাট সেভ হবে
        query = "INSERT INTO users (sender_id, history, last_seen) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE history=%s, last_seen=%s"
        cursor.execute(query, (sender_id, history_json, int(time.time()), history_json, int(time.time())))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"DB Save Error: {e}")

# ================= এপিআই কল লজিক (Error Handled) =================

def get_key(api_type, keys_list):
    global indices
    with index_lock:
        if not keys_list: return None
        key = keys_list[indices[api_type]]
        indices[api_type] = (indices[api_type] + 1) % len(keys_list)
        return key

def try_gemini(history, text):
    key = get_key("gemini", GEMINI_KEYS)
    if not key: return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": history + [{"role": "user", "parts": [{"text": text}]}]
        }
        res = requests.post(url, json=payload, timeout=12)
        data = res.json()
        if 'candidates' in data:
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
    except: return None

def try_groq(text):
    key = get_key("groq", GROQ_KEYS)
    if not key: return None
    try:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}]
        }
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=12)
        data = res.json()
        if 'choices' in data:
            return data['choices'][0]['message']['content'].strip()
    except: return None

# ================= প্রসেসিং ও সেন্ডিং =================

def process_and_send(sender_id, text):
    # ডাটাবেজ থেকে হিস্ট্রি আনা
    history = get_db_history(sender_id)

    # ব্যাকআপ লজিক
    reply = try_gemini(history, text)
    if not reply: reply = try_groq(text)

    if reply:
        reply = " ".join(reply.split()).replace('\n', ' ')
        if not reply.endswith(('।', '?', '!')): reply += '।'

        # সেন্ড করার আগে ২ সেকেন্ড ওয়েট (স্বাভাবিক ভাব আনতে)
        time.sleep(2)

        # ফেসবুক মেসেঞ্জারে সেন্ড
        fb_url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        requests.post(fb_url, json={"recipient": {"id": sender_id}, "message": {"text": reply}})

        # হিস্ট্রি আপডেট ও ডাটাবেজে সেভ
        history.append({"role": "user", "parts": [{"text": text}]})
        history.append({"role": "model", "parts": [{"text": reply}]})
        save_db_history(sender_id, history)

# ================= রাউটস =================

@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Failed", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                if "message" in event and "text" in event["message"]:
                    threading.Thread(target=process_and_send, args=(event["sender"]["id"], event["message"]["text"])).start()
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
