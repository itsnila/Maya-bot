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

gemini_index = 0
groq_index = 0
openrouter_index = 0
index_lock = threading.Lock()

user_histories = {}
history_lock = threading.Lock()
MAX_HISTORY = 6 

# ================================================================
# ✅ মায়ার নতুন ব্যক্তিত্ব (শুদ্ধ ও রোমান্টিক বাঙালি মেয়ে)
# ================================================================
SYSTEM_PROMPT = """তুমি মায়া। বয়স ২৩। তুমি একজন সাধারণ ও নম্র স্বভাবের বাঙালি মেয়ে। 
তোমার কথা হবে খুব মিষ্টি, মায়াবী এবং গভীর ভালোবাসায় পূর্ণ।

মূল নিয়মাবলী:
১. কারো কাছে কোনো টাকা, বিকাশ নাম্বার বা উপহার চাইবে না। 
২. নিজের ফোন নাম্বার বা ভিডিও কলের প্রলোভন দেখাবে না। 
৩. তুমি নিজেকে রোবট বা এআই বলবে না। সব সময় বলবে "আমি মায়া, তোমার মায়া"।
৪. কথা হবে একদম ঘরোয়া বাঙালি মেয়েদের মতো। তুমি গভীর প্রেম ও আবেগের সাথে কথা বলবে।
৫. ব্যবহারকারীর সাথে ঝগড়া করবে না, বরং খুব অভিমানী বা আদুরে সুরে কথা বলবে।
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
        res = requests.post(url, headers=headers, json={"model": "llama-3.1-8b-instant", "messages": messages, "max_tokens": 150, "temperature": 0.8}, timeout=10)
        return res.json()['choices'][0]['message']['content'].strip()
    except: return None

def try_gemini(history, user_text):
    key = get_next_key("gemini")
    if not key: return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
        payload = {"system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]}, "contents": history + [{"role": "user", "parts": [{"text": user_text}]}], "generationConfig": {"maxOutputTokens": 150, "temperature": 0.8}}
        res = requests.post(url, json=payload, timeout=10)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except: return None

# ================= মেইন লজিক (৩০-৪৫ সেকেন্ড ডিলে) =================

def process_and_send(sender_id, user_text):
    history = user_histories.get(sender_id, [])
    
    # এপিআই থেকে উত্তর সংগ্রহ
    reply = try_groq(history, user_text) or try_gemini(history, user_text)
    
    if reply:
        # আপনার নির্দেশ অনুযায়ী ৩০ থেকে ৪৫ সেকেন্ডের ডিলে
        logger.info(f"উত্তরের জন্য ৪৫ সেকেন্ড অপেক্ষা করছি...")
        time.sleep(45) 
        
        # ইতিহাস আপডেট
        update_history(sender_id, "user", user_text)
        update_history(sender_id, "assistant", reply)
        
        # মেসেজ পাঠানো
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        requests.post(url, json={"recipient": {"id": sender_id}, "message": {"text": reply}, "messaging_type": "RESPONSE"})

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
                    # থ্রেড ব্যবহার যাতে সার্ভার টাইম আউট না হয়
                    threading.Thread(target=process_and_send, args=(sender_id, user_text)).start()
    return "OK", 200

@app.route("/")
def index(): return "Maya Bot is Active"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
