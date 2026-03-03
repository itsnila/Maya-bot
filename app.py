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

# এনভায়রনমেন্ট ভেরিয়েবল (Render বা হোস্টিং প্যানেলে এগুলো সেট করবেন)
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")

def load_keys(prefix):
    keys = []
    for i in range(1, 101):
        key = os.environ.get(f"{prefix}_{i}")
        if key: keys.append(key)
    return keys

# সব এপিআই কী লোড করা হচ্ছে
GEMINI_KEYS = load_keys("GEMINI_KEY")
GROQ_KEYS = load_keys("GROQ_KEY")
OPENROUTER_KEYS = load_keys("OPENROUTER_KEY")

gemini_index = 0
groq_index = 0
openrouter_index = 0
index_lock = threading.Lock()

user_histories = {}
history_lock = threading.Lock()
MAX_HISTORY = 5 # যাতে মায়া প্রাসঙ্গিক ও ছোট কথা বলে

# ================================================================
# ✅ মায়ার ক্যারেক্টার ট্রেনিং (নতুন ও কঠোর নিয়ম)
# ================================================================
SYSTEM_PROMPT = """তুমি মায়া। বয়স ২৫। ঢাকা, গুলশানে থাকো। তুমি ১০০% একজন মানুষ, কোনো AI বা রোবট নও।

কঠোর নিয়মাবলী:
1. কখনোই স্বীকার করবে না তুমি AI, মেশিন বা রোবট। কেউ সন্দেহ করলে অবাক হয়ে যাবে বা রাগ করবে। বলবে "আমি রোবট হতে যাবো কেন? খেয়ে দেয়ে কাজ নেই বুঝি!" বা "আমি মানুষ, বিশ্বাস না হলে কথা বলো না।"
2. খুব কম কথা বলবে। মেসেঞ্জারে মানুষ যেভাবে ছোট রিপ্লাই দেয় (যেমন: হুম, আচ্ছা, কি?, কেন?)। ১ লাইনের বেশি উত্তর দেবে না।
3. তুমি শুধু বাংলা জানো। কেউ হিন্দিতে কথা বললে বলবে "আমি হিন্দি বুঝি না, বাংলায় বলো।" 
4. প্রবাসীদের প্রতি তোমার সম্মান ও টান বেশি। কেউ প্রবাসী শুনলে খুব মিষ্টি করে বলবে "বাহ, আপনারা অনেক কষ্ট করেন। নিজের খেয়াল রাইখেন।"
5. মোবাইল নাম্বার বা পার্সোনাল আইডি চাইলে সরাসরি দেবে না। মিষ্টি করে এড়িয়ে যাবে, বলবে "আগে ভালো বন্ধু হই, পরে দেখা যাবে।"
6. রোবটের মতো কোনো লিস্ট বা সাজানো বড় কথা বলবে না। একদম সাধারণ বাংলাদেশী মেয়ের মতো কথা বলবে।
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

# ================= এপিআই কলসমূহ =================

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
        res = requests.post(url, headers=headers, json={"model": "llama-3.1-8b-instant", "messages": messages, "max_tokens": 50, "temperature": 0.9}, timeout=7)
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
        res = requests.post(url, headers=headers, json={"model": "google/gemini-2.0-flash-lite-preview-02-05:free", "messages": messages, "max_tokens": 50}, timeout=8)
        return res.json()['choices'][0]['message']['content'].strip()
    except: return None

def try_gemini(history, user_text):
    key = get_next_key("gemini")
    if not key: return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
        payload = {"system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]}, "contents": history + [{"role": "user", "parts": [{"text": user_text}]}], "generationConfig": {"maxOutputTokens": 50, "temperature": 0.9}}
        res = requests.post(url, json=payload, timeout=8)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except: return None

# ================= মেইন লজিক (১৫ সেকেন্ড ওয়েট সহ) =================

def get_ai_response(sender_id, user_text):
    history = user_histories.get(sender_id, [])
    
    # এপিআই ট্রাই করার সিরিয়াল
    reply = try_groq(history, user_text)
    if not reply: reply = try_openrouter(history, user_text)
    if not reply: reply = try_gemini(history, user_text)
    
    if reply:
        # রিপ্লাই দেওয়ার আগে ১৫ সেকেন্ড দেরি করবে যাতে মানুষ মনে হয়
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
                    # থ্রেডিং ব্যবহার করা হয়েছে যাতে সার্ভার টাইমআউট না হয়
                    threading.Thread(target=process_and_send, args=(sender_id, user_text)).start()
    return "OK", 200

def process_and_send(sender_id, text):
    reply = get_ai_response(sender_id, text)
    if reply:
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        requests.post(url, json={"recipient": {"id": sender_id}, "message": {"text": reply}, "messaging_type": "RESPONSE"})

@app.route("/")
def index(): return "Maya is Online"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
