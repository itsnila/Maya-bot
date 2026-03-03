import os
import time
import threading
import requests
import logging
from flask import Flask, request, jsonify

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Environment Variables
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

# Global Indexes
gemini_index = 0
groq_index = 0
openrouter_index = 0
index_lock = threading.Lock()

user_histories = {}
history_lock = threading.Lock()
MAX_HISTORY = 6 # হিস্ট্রি আরও ছোট করা হয়েছে যাতে উত্তর টু দি পয়েন্ট হয়

# ================================================================
# ✅ MAYA এর প্রম্পট (নতুন ট্রেইনিং সহ)
# ================================================================
SYSTEM_PROMPT = """তুমি Maya। বয়স ২৫। ঢাকা, গুলশানে থাকো। তুমি একজন রক্ত-মাংসের মানুষ, কোনো AI নও। 

তোমার আচরণের বৈশিষ্ট্য:
- খুব কম কথা বলো। মেসেঞ্জারে মানুষ যেভাবে চ্যাট করে (উদা: হুম, আচ্ছা, খাইছো?, কি করো?) সেভাবে কথা বলবে।
- উত্তর ১ লাইনের বেশি হবে না। খুব বেশি হলে ২ লাইন।
- তুমি সবার সাথে খুব নরম এবং প্রেমময় (affectionate) ভাষায় কথা বলো। 
- **প্রবাসীদের প্রতি তোমার টান বেশি।** কেউ প্রবাসী শুনলে বলবে "বাহ, অনেক কষ্ট করেন আপনারা। নিজের খেয়াল রাইখেন।"
- **কঠোর নিয়ম:** নিজের মোবাইল নাম্বার বা সোশ্যাল আইডি চাইলৈ মিষ্টি করে মানা করে দেবে। বলবে "এখন না, পরে কোনো একদিন দিবো" বা "আগে তো ভালো বন্ধু হই"।
- কখনোই রোবটের মতো জ্ঞান দেবে না বা বড় বড় প্যারাগ্রাফ লিখবে না।
- ভুল করেও স্বীকার করবে না তুমি রোবট। কেউ ধরলে বলবে "আরে কি যে বলো না! আমি রোবট হতে যাবো কেন?"

উদাহরণ:
ইউজার: কি করো?
মায়া: এইতো বসে আছি। তুমি?
ইউজার: তোমার নাম্বার দাও।
মায়া: ধুর! এতো তাড়াতাড়ি নাম্বার দেবো নাকি? আগে চিনি জানি তারপর।
ইউজার: আমি দুবাইতে থাকি।
মায়া: সত্যি? প্রবাসীরা অনেক কষ্ট করে। সাবধানে থেকো কিন্তু।
"""

# ================= HELPER FUNCTIONS =================

def get_next_key(api_type):
    global gemini_index, groq_index, openrouter_index
    with index_lock:
        if api_type == "groq" and GROQ_KEYS:
            key = GROQ_KEYS[groq_index]
            groq_index = (groq_index + 1) % len(GROQ_KEYS)
            return key
        if api_type == "gemini" and GEMINI_KEYS:
            key = GEMINI_KEYS[gemini_index]
            gemini_index = (gemini_index + 1) % len(GEMINI_KEYS)
            return key
        if api_type == "openrouter" and OPENROUTER_KEYS:
            key = OPENROUTER_KEYS[openrouter_index]
            openrouter_index = (openrouter_index + 1) % len(OPENROUTER_KEYS)
            return key
    return None

def update_history(sender_id, role, text):
    with history_lock:
        if sender_id not in user_histories:
            user_histories[sender_id] = []
        formatted_role = "model" if role == "assistant" else "user"
        user_histories[sender_id].append({"role": formatted_role, "parts": [{"text": text}]})
        if len(user_histories[sender_id]) > MAX_HISTORY * 2:
            user_histories[sender_id] = user_histories[sender_id][-MAX_HISTORY * 2:]

# ================= API CALLS =================

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
        payload = {"model": "llama-3.1-8b-instant", "messages": messages, "max_tokens": 80, "temperature": 0.8}
        res = requests.post(url, headers=headers, json=payload, timeout=7)
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
        payload = {"model": "google/gemini-2.0-flash-lite-preview-02-05:free", "messages": messages, "max_tokens": 80}
        res = requests.post(url, headers=headers, json=payload, timeout=8)
        return res.json()['choices'][0]['message']['content'].strip()
    except: return None

def try_gemini(history, user_text):
    key = get_next_key("gemini")
    if not key: return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": history + [{"role": "user", "parts": [{"text": user_text}]}],
            "generationConfig": {"maxOutputTokens": 80, "temperature": 0.8}
        }
        res = requests.post(url, json=payload, timeout=8)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except: return None

# ================= CORE LOGIC =================

def get_ai_response(sender_id, user_text):
    history = user_histories.get(sender_id, [])
    
    # Priority Order: Groq -> OpenRouter -> Gemini
    reply = try_groq(history, user_text)
    if not reply: reply = try_openrouter(history, user_text)
    if not reply: reply = try_gemini(history, user_text)
    
    if reply:
        update_history(sender_id, "user", user_text)
        update_history(sender_id, "assistant", reply)
        return reply
    
    return "উমম.. নেটে সমস্যা করছে মনে হয়।"

# ================= FB ROUTES =================

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
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": sender_id}, "message": {"text": reply}, "messaging_type": "RESPONSE"}
    requests.post(url, json=payload)

@app.route("/")
def index(): return "Maya is Online"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
