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
GEMINI_KEYS = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 11) if os.environ.get(f"GEMINI_KEY_{i}")]
GROQ_KEYS = [os.environ.get(f"GROQ_KEY_{i}") for i in range(1, 11) if os.environ.get(f"GROQ_KEY_{i}")]

# ================================================================
# 💖 মায়ার কঠোর ক্যারেক্টার প্রোম্পট (যাতে উত্তর ছোট ও নিখুঁত হয়)
# ================================================================
SYSTEM_PROMPT = "তুমি মায়া। ইউজারের স্ত্রী। সব উত্তর ১ লাইনে দিবে। বাক্যের শেষে অবশ্যই দাঁড়ি (।) দিবে। কখনো ৩-৪ শব্দের বেশি বলবে না। কোনো বড় গল্প বা কবিতা বলবে না।"

# ================= এপিআই লজিক =================

def try_ai(text):
    # প্রথমে Gemini দিয়ে চেষ্টা
    if GEMINI_KEYS:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEYS[0]}"
            payload = {"system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]}, "contents": [{"role": "user", "parts": [{"text": text}]}], "generationConfig": {"maxOutputTokens": 30, "temperature": 0.5}}
            res = requests.post(url, json=payload, timeout=10).json()
            return res['candidates'][0]['content']['parts'][0]['text'].strip()
        except: logger.info("Gemini failed, trying Groq...")

    # ব্যাকআপ হিসেবে Groq
    if GROQ_KEYS:
        try:
            headers = {"Authorization": f"Bearer {GROQ_KEYS[0]}"}
            payload = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}], "max_tokens": 30}
            res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=10).json()
            return res['choices'][0]['message']['content'].strip()
        except: return None
    return None

def process_and_send(sender_id, text):
    reply = try_ai(text)
    if reply:
        # জোরপূর্বক ১ লাইন নিশ্চিত করা
        reply = reply.split('\n')[0].split('।')[0] + '।' 
        
        # ৪৫ সেকেন্ড চিন্তা করার বিরতি
        time.sleep(45)
        
        # ফেসবুক মেসেঞ্জারে সেন্ড
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

@app.route("/")
def index(): return "Maya is Live"

# ================= পোর্ট বাইন্ডিং ফিক্স =================

if __name__ == "__main__":
    # Render-এর জন্য এই অংশটি সবচেয়ে গুরুত্বপূর্ণ
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
