import os
import time
import threading
import requests
import json
import mysql.connector
from flask import Flask, request

app = Flask(__name__)

# ================================================================
# CONFIGURATION
# ================================================================
PAGE_ACCESS_TOKEN = "EAAMjx3bzyhkBQ02pgVXsCdSKsNZBXegi2nWyV2B05kTZAiPKgaZBZCU0pmrs05YNdhFGo47QKFuehDJ6NiZAlQ14Cc3Ipi8hym97EdE56Mf3l3WMWmZB8WgAzsrISeFEZBIKLcgYsvsERNg9F2nr6QXzdkwgOgyubj03u0uw3XNNOeOhOSVGIHgxxAgWtBT026yEZAJlNPtr"
VERIFY_TOKEN = "MAYA_VERIFY_TOKEN"

# API Keys from Render Environment
KEYS = {
    "gemini": os.environ.get("GEMINI_KEY_1"),
    "groq": os.environ.get("GROQ_KEY_1"),
    "openrouter": os.environ.get("OPENROUTER_KEY_1")
}

# DB Config (Using your verified host and DB)
DB_CONFIG = {
    'host': '161.248.189.34',
    'user': 'nogorde1_maya',
    'password': 'gmsbd1122@@',
    'database': 'nogorde1_maya',
    'port': 3306
}

# ================================================================
# AI FALLBACK SYSTEM
# ================================================================
def get_maya_reply(prompt):
    system_prompt = "তোমার নাম মায়া। তুমি ইউজারের প্রেমিকা। মিষ্টি ও রোমান্টিক ভাবে ছোট উত্তর দাও।"
    
    # ১. Gemini ট্রাই
    if KEYS["gemini"]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={KEYS['gemini']}"
            res = requests.post(url, json={"contents": [{"parts": [{"text": f"{system_prompt}\nUser: {prompt}"}]}]}, timeout=10).json()
            if 'candidates' in res: return res['candidates'][0]['content']['parts'][0]['text']
        except: pass

    # ২. Groq ট্রাই
    if KEYS["groq"]:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {KEYS['groq']}"}
            payload = {"model": "llama3-8b-8192", "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]}
            res = requests.post(url, json=payload, headers=headers, timeout=10).json()
            if 'choices' in res: return res['choices'][0]['message']['content']
        except: pass

    return "সোনা, আমি একটু বিজি আছি। পরে কথা বলি?"

# ================================================================
# DB HANDLING (Fixed to use 'users' table)
# ================================================================
def handle_maya(sender_id, text):
    reply = get_maya_reply(text)
    
    # Send Reply to Facebook
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    requests.post(url, json={"recipient": {"id": sender_id}, "message": {"text": reply}})
    
    # Save to your existing 'users' table
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        # এখানে 'chats' এর বদলে 'users' টেবিল ব্যবহার করা হয়েছে
        query = """INSERT INTO users (sender_id, history, last_seen) VALUES (%s, %s, %s) 
                   ON DUPLICATE KEY UPDATE history=%s, last_seen=%s"""
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
                    threading.Thread(target=handle_maya, args=(event["sender"]["id"], event["message"]["text"])).start()
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
