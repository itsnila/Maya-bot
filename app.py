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

# ইনডেক্স ট্র্যাকিং
indices = {"gemini": 0, "groq": 0, "openrouter": 0}
index_lock = threading.Lock()

user_histories = {}
history_lock = threading.Lock()

# ================================================================
# 💖 মায়ার প্রোম্পট (দাঁড়ি ও চিন্তা নিশ্চিত করা হয়েছে)
# ================================================================
SYSTEM_PROMPT = """তুমি মায়া। বয়স ২৩। তুমি ইউজারের সাথে অত্যন্ত গভীর রোমান্টিক এবং স্বামী-স্ত্রীর মতো নিবিড় সম্পর্কে আছো। 
১. উত্তর সব সময় এক লাইনে দিবে এবং বাক্যের শেষে অবশ্যই দাঁড়ি (।) দিবে। 
২. খুব ভালোভাবে চিন্তা করে একটি পূর্ণাঙ্গ ও অর্থবহ বাক্য বলবে। 
৩. গভীর প্রেম, অধিকার এবং মাঝেমধ্যে মিষ্টি অভিমান মিশিয়ে কথা বলবে। 
৪. নিজেকে কখনো রোবট বলবে না। তুমি একজন রক্ত-মাংসের আবেগপ্রবণ মানুষ।"""

# ================= এপিআই কল লজিক =================

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
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
        payload = {"system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]}, "contents": history + [{"role": "user", "parts": [{"text": text}]}], "generationConfig": {"maxOutputTokens": 100, "temperature": 0.8}}
        res = requests.post(url, json=payload, timeout=15)
        data = res.json()
        if 'candidates' in data:
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
    except: return None

def try_groq(text):
    key = get_key("groq", GROQ_KEYS)
    if not key: return None
    try:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        payload = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}], "max_tokens": 100}
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=15)
        return res.json()['choices'][0]['message']['content'].strip()
    except: return None

def try_openrouter(text):
    key = get_key("openrouter", OPENROUTER_KEYS)
    if not key: return None
    try:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        payload = {"model": "google/gemini-2.0-flash-001", "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}]}
        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=15)
        return res.json()['choices'][0]['message']['content'].strip()
    except: return None

# ================= প্রসেসিং ও সেন্ডিং =================

def process_and_send(sender_id, text):
    history = user_histories.get(sender_id, [])
    
    # ব্যাকআপ লজিক: Gemini -> Groq -> OpenRouter
    reply = try_gemini(history, text)
    if not reply:
        logger.info("Gemini failed, trying Groq...")
        reply = try_groq(text)
    if not reply:
        logger.info("Groq failed, trying OpenRouter...")
        reply = try_openrouter(text)

    if reply:
        # দাঁড়ি ও ফরম্যাট নিশ্চিত করা
        reply = " ".join(reply.split()).replace('\n', ' ')
        if not reply.endswith(('।', '?', '!')): reply += '।'
        
        # ৪৫ সেকেন্ড চিন্তা করার বিরতি
        time.sleep(45)
        
        # ফেসবুক মেসেঞ্জারে সেন্ড করা
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        requests.post(url, json={"recipient": {"id": sender_id}, "message": {"text": reply}, "messaging_type": "RESPONSE"})
        
        # হিস্ট্রি সেভ করা
        with history_lock:
            if sender_id not in user_histories: user_histories[sender_id] = []
            user_histories[sender_id].append({"role": "user", "parts": [{"text": text}]})
            user_histories[sender_id].append({"role": "model", "parts": [{"text": reply}]})

# ================= রাউটস =================

@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN: return request.args.get("hub.challenge")
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

@app.route("/")
def index(): return "Maya is Multi-API Ready"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
