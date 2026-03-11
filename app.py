import os
import time
import threading
import requests
import mysql.connector
from flask import Flask, request

app = Flask(__name__)

# ================================================================
# CONFIGURATION
# ================================================================
PAGE_ACCESS_TOKEN = "EAAMjx3bzyhkBQ02pgVXsCdSKsNZBXegi2nWyV2B05kTZAiPKgaZBZCU0pmrs05YNdhFGo47QKFuehDJ6NiZAlQ14Cc3Ipi8hym97EdE56Mf3l3WMWmZB8WgAzsrISeFEZBIKLcgYsvsERNg9F2nr6QXzdkwgOgyubj03u0uw3XNNOeOhOSVGIHgxxAgWtBT026yEZAJlNPtr"
VERIFY_TOKEN = "MAYA_VERIFY_TOKEN"

# সরাসরি এপিআই কী (লগ অনুযায়ী সঠিকগুলো বসানো হয়েছে)
GEMINI_API_KEY = "AIzaSy..." # আপনার সঠিক Gemini Key দিন
GROQ_API_KEY = "gsk_..."      # আপনার সঠিক Groq Key দিন

# ডেটাবেজ কনফিগ (আপনার ভেরিফাইড ইউজার অনুযায়ী)
DB_CONFIG = {
    'host': '161.248.189.34',
    'user': 'nogorde1_maya',
    'password': 'gmsbd1122@@',
    'database': 'nogorde1_maya',
    'port': 3306
}

# ================================================================
# AI ENGINE
# ================================================================
def get_maya_response(user_text):
    system_prompt = "তুমি মায়া। তুমি ইউজারের প্রেমিকা। মিষ্টি করে ছোট রোমান্টিক উত্তর দাও।"
    
    # ১. Gemini ট্রাই (প্রাইমারি)
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents": [{"parts": [{"text": f"{system_prompt}\nUser: {user_text}"}]}]}
        res = requests.post(url, json=payload, timeout=8).json()
        return res['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        print(f"Gemini Error: {e}")

    # ২. Groq ট্রাই (ব্যাকআপ)
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
        payload = {
            "model": "llama3-8b-8192",
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_text}]
        }
        res = requests.post(url, json=payload, headers=headers, timeout=8).json()
        return res['choices'][0]['message']['content']
    except Exception as e:
        print(f"Groq Error: {e}")

    return "সোনা, আমি একটু বিজি আছি। পরে কথা বলি?"

# ================================================================
# CORE LOGIC
# ================================================================
def send_fb_reply(sender_id, text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    requests.post(url, json={"recipient": {"id": sender_id}, "message": {"text": text}})

def process_message(sender_id, user_text):
    reply = get_maya_response(user_text)
    send_fb_reply(sender_id, reply)
    
    # ডেটাবেজে সেভ
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        query = "INSERT INTO users (sender_id, history, last_seen) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE history=%s, last_seen=%s"
        cursor.execute(query, (sender_id, reply[:100], int(time.time()), reply[:100], int(time.time())))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        return "Forbidden", 403
    
    data = request.json
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                if "message" in event and "text" in event["message"]:
                    threading.Thread(target=process_message, args=(event["sender"]["id"], event["message"]["text"])).start()
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
