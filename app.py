import os
import time
import threading
import requests
import logging
from flask import Flask, request

# লগিং সেটআপ
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# এনভায়রনমেন্ট ভেরিয়েবল
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")

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
user_histories = {}
history_lock = threading.Lock()

# ================================================================
# 💖 মায়ার কঠোর নির্দেশনা (যাতে ছোট ও নিখুঁত উত্তর আসে)
# ================================================================
SYSTEM_PROMPT = "তুমি মায়া। ইউজারের স্ত্রী। সব উত্তর ১ লাইনে দিবে। বাক্যের শেষে অবশ্যই দাঁড়ি (।) দিবে। কখনো বড় উত্তর দিবে না।"

# ================= এপিআই কল লজিক =================

def try_gemini(history, text):
    key = GEMINI_KEYS[0] if GEMINI_KEYS else None
    if not key: return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
        payload = {"system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]}, "contents": history + [{"role": "user", "parts": [{"text": text}]}], "generationConfig": {"maxOutputTokens": 50, "temperature": 0.7}}
        res = requests.post(url, json=payload, timeout=15).json()
        return res['candidates'][0]['content']['parts'][0]['text'].strip()
    except: return None

def try_groq(text):
    key = GROQ_KEYS[0] if GROQ_KEYS else None
    if not key: return None
    try:
        headers = {"Authorization": f"Bearer {key}"}
        payload = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}], "max_tokens": 50}
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=15).json()
        return res['choices'][0]['message']['content'].strip()
    except: return None

def process_and_send(sender_id, text):
    # ব্যাকআপ লজিক
    reply = try_gemini(user_histories.get(sender_id, []), text) or try_groq(text)

    if reply:
        # জোরপূর্বক এক লাইন এবং দাঁড়ি নিশ্চিত করা
        reply = reply.split('\n')[0] # প্রথম লাইনের পর সব বাদ
        if not reply.endswith(('।', '?', '!')): reply += '।'
        
        # ৪৫ সেকেন্ড চিন্তা করার বিরতি
        time.sleep(45)
        
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        requests.post(url, json={"recipient": {"id": sender_id}, "message": {"text": reply}})

# ================= রাউটস =================
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return request.args.get("hub.challenge") if request.args.get("hub.verify_token") == VERIFY_TOKEN else ("Failed", 403)
    
    data = request.json
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                if "message" in event and "text" in event["message"]:
                    threading.Thread(target=process_and_send, args=(event["sender"]["id"], event["message"]["text"])).start()
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
