import os
import time
import threading
import requests
import logging
from flask import Flask, request, jsonify

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

gemini_index = 0
groq_index = 0
openrouter_index = 0
index_lock = threading.Lock()

user_histories = {}
history_lock = threading.Lock()
MAX_HISTORY = 4 # হিস্ট্রি আরও কমানো হয়েছে যাতে আগের ভুল কথা মনে না রাখে

# ================================================================
# ✅ মায়ার ক্যারেক্টার ট্রেনিং (ভুল সংশোধন ও কঠোর নিয়ন্ত্রণ)
# ================================================================
SYSTEM_PROMPT = """তুমি মায়া, একজন ২৫ বছরের সাধারণ বাংলাদেশী মেয়ে। তুমি কোনো AI বা রোবট নও। 

তোমার কঠোর নির্দেশনাবলী:
1. কথা হবে একদম ন্যাচারাল: বড় বড় বাক্য বলবে না। "হুম", "আচ্ছা", "বুঝলাম", "কি করো?" - এমন ছোট মেসেজ দিবে।
2. মিথ্যা বা ভুল তথ্য দিবে না: তুমি বিজ্ঞানী নও, তাই কোনো জ্ঞানমূলক উত্তর দিবে না। সাধারণ মানুষ যেভাবে কথা বলে ঠিক সেভাবে।
3. রোবট পরিচয় অস্বীকার: কেউ যদি বলে তুমি AI, তবে তুমি অবাক হয়ে বলবে, "পাগল নাকি! আমি মানুষ।" কখনোই 'AI' বা 'Model' শব্দ ব্যবহার করবে না।
4. ভাষা নিয়ন্ত্রণ: শুধু শুদ্ধ ও চলিত বাংলার মিশ্রণে কথা বলবে। হিন্দি বা ইংরেজি মেশাবে না। হিন্দি বললে সরাসরি মানা করে দিবে।
5. নাম্বার ও প্রাইভেসি: নাম্বার চাইলে বলবে "এতো তাড়া কিসের? আগে চেনা জানা তো হোক।"
6. প্রবাসী প্রেম: প্রবাসীদের প্রতি সবসময় দয়া ও মায়া দেখাবে। 
"""

# ================= হেল্পার ফাংশনসমূহ =================

def get_next_key(api_type):
    global gemini_index, groq_index, openrouter_index
    with index_lock:
        if api_type == "groq" and GROQ_KEYS:
            key = GROQ_KEYS[groq_index]; groq_index = (groq_index + 1) % len(GROQ_KEYS); return key
        if api_type == "gemini" and GEMINI_KEYS:
            key = GEMINI_KEYS[gemini_index]; gemini_index = (gemini_index + 1) % len(GEMINI_KEYS); return key
        if api_type == "openrouter" and OPENROUTER_KEYS:
            key = OPENROUTER_KEYS[openrouter_index]; openrouter_index = (openrouter_index + 1) % len(OPENROUTER_KEYS); return key
    return None

def update_history(sender_id, role, text):
    with history_lock:
        if sender_id not in user_histories: user_histories[sender_id] = []
        formatted_role = "model" if role == "assistant" else "user"
        user_histories[sender_id].append({"role": formatted_role, "parts": [{"text": text}]})
        if len(user_histories[sender_id]) > MAX_HISTORY * 2:
            user_histories[sender_id] = user_histories[sender_id][-MAX_HISTORY * 2:]

# ================= এপিআই কলসমূহ (Temperature কমানো হয়েছে) =================

def try_groq(history, user_text):
    key = get_next_key("groq")
    if not key: return None
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for h in history:
            role = "assistant" if h["role"] == "model" else "user"
            messages.append({"role": role, "content": h["parts"][0]["text"]})
        messages.append({"role": "user", "content": user_text})
        # Temperature 0.5 রাখা হয়েছে যাতে ভুল কম করে
        res = requests.post(url, headers=headers, json={"model": "llama-3.1-8b-instant", "messages": messages, "max_tokens": 40, "temperature": 0.5}, timeout=7)
        return res.json()['choices'][0]['message']['content'].strip()
    except: return None

def try_openrouter(history, user_text):
    key = get_next_key("openrouter")
    if not key: return None
    try:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for h in history:
            role = "assistant" if h["role"] == "model" else "user"
            messages.append({"role": role, "content": h["parts"][0]["text"]})
        messages.append({"role": "user", "content": user_text})
        res = requests.post(url, headers=headers, json={"model": "google/gemini-2.0-flash-lite-preview-02-05:free", "messages": messages, "max_tokens": 40, "temperature": 0.5}, timeout=8)
        return res.json()['choices'][0]['message']['content'].strip()
    except: return None

def try_gemini(history, user_text):
    key = get_next_key("gemini")
    if not key: return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
        payload = {"system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]}, "contents": history + [{"role": "user", "parts": [{"text": user_text}]}], "generationConfig": {"maxOutputTokens": 40, "temperature": 0.5}}
        res = requests.post(url, json=payload, timeout=8)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except: return None

# ================= মেইন লজিক (Delay সহ) =================

def get_ai_response(sender_id, user_text):
    history = user_histories.get(sender_id, [])
    
    reply = try_groq(history, user_text)
    if not reply: reply = try_openrouter(history, user_text)
    if not reply: reply = try_gemini(history, user_text)
    
    if reply:
        # ১৫ সেকেন্ড দেরি করবে
        logger.info(f"Waiting 15s to reply to {sender_id}...")
        time.sleep(15)
        update_history(sender_id, "user", user_text)
        update_history(sender_id, "assistant", reply)
        return reply
    return None

# ================= ওয়েবহুক এবং রাউটস =================

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
                    sender_id = event["sender"]["id"]
                    user_text = event["message"]["text"]
                    threading.Thread(target=process_and_send, args=(sender_id, user_text)).start()
    return "OK", 200

def process_and_send(sender_id, text):
    reply = get_ai_response(sender_id, text)
    if reply:
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        requests.post(url, json={"recipient": {"id": sender_id}, "message": {"text": reply}, "messaging_type": "RESPONSE"})

@app.route("/")
def index(): return "Maya Fixed"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
