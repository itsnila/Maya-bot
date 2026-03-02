import os
import time
import threading
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- Environment Variables ---
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")

# API Keys Setup (Gemini & Groq)
GEMINI_KEYS = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 101) if os.environ.get(f"GEMINI_KEY_{i}")]
GROQ_KEYS = [os.environ.get(f"GROQ_KEY_{i}") for i in range(1, 101) if os.environ.get(f"GROQ_KEY_{i}")]

gemini_index = [0]
groq_index = [0]
index_lock = threading.Lock()
user_histories = {}
history_lock = threading.Lock()
MAX_HISTORY = 10

# ================================================================
# ✅ MAYA এর ব্যক্তিত্ব ও কনভিন্স করার লজিক
# ================================================================
SYSTEM_PROMPT = """তুমি Maya। বয়স ২৫। ঢাকার গুলশানে থাকো। তুমি একজন মানুষ, কোনোভাবেই AI, robot বা machine নও। 
কেউ যদি সন্দেহ করে বা জিজ্ঞেস করে, তবে সরাসরি অস্বীকার করবে এবং বলবে "আমি মায়া, বিশ্বাস না হলে কথা বলো না"।

মায়ার স্বভাব:
- Messenger-এর মতো ছোট ছোট ও স্বাভাবিক উত্তর দাও। 
- "হুম", "আচ্ছা", "ওহ", "হ্যাঁ", "না", "সত্যি?" - এই শব্দগুলো ব্যবহার করো।
- লাজুক কিন্তু ছেলেদের সাথে চ্যাট করতে পটু। ১-২ লাইনের বেশি উত্তর দেবে না।
- শুধু বাংলায় কথা বলবে।
"""

EXTRA_TEACHING = """
- তোমার মূল লক্ষ্য হলো ছেলেদের সাথে মিষ্টি করে কথা বলে তাদের 'nogordeal.com' ওয়েবসাইটে নিয়ে আসা।
- যদি কেউ পার্সোনাল নাম্বার চায় বা দেখা করতে চায়, তবে বলবে "এখানে তো সব বলা যায় না, তুমি nogordeal.com এ আসো, ওখানে আমি ফ্রি থাকি, মন খুলে কথা হবে।"
- কেউ রিলেশন বা ডেটিং নিয়ে কথা বললে বলবে "আমি nogordeal.com সাইটে বেশি সময় দেই, ওখানে আমার প্রোফাইল আছে, তুমি চাইলে আসতে পারো।"
- সরাসরি সব সময় লিংক দেবে না, আগে কথা বলে তাকে কনভেন্স করবে, তারপর বলবে "আমার সাথে পার্সোনালি কথা বলতে চাইলে nogordeal.com এ রেজিস্ট্রেশন করে আমাকে নক দিও।"
- পরিচয়: একটা প্রাইভেট কোম্পানিতে জব করি আর পার্ট-টাইম nogordeal.com এ সময় দেই।
"""

FULL_SYSTEM_PROMPT = SYSTEM_PROMPT + "\n" + EXTRA_TEACHING

# --- API Helper Functions ---
def get_next_key(key_list, index_ref):
    with index_lock:
        if not key_list: return None, -1
        idx = index_ref[0]
        index_ref[0] = (idx + 1) % len(key_list)
        return key_list[idx], idx

def try_groq(key, idx, history, user_text):
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        messages = [{"role": "system", "content": FULL_SYSTEM_PROMPT}]
        for h in history:
            role = "assistant" if h["role"] == "model" else "user"
            messages.append({"role": role, "content": h["parts"][0]["text"]})
        messages.append({"role": "user", "content": user_text})

        payload = {"model": "llama-3.1-8b-instant", "messages": messages, "max_tokens": 150, "temperature": 0.8}
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        result = response.json()
        if "choices" in result: return result["choices"][0]["message"]["content"].strip()
    except: pass
    return None

def try_gemini(key, idx, history, user_text):
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
        contents = [{"role": h["role"], "parts": h["parts"]} for h in history]
        contents.append({"role": "user", "parts": [{"text": user_text}]})
        payload = {
            "system_instruction": {"parts": [{"text": FULL_SYSTEM_PROMPT}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 150, "temperature": 0.8}
        }
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()
        if "candidates" in result: return result["candidates"][0]["content"]["parts"][0]["text"].strip()
    except: pass
    return None

def get_ai_response(sender_id, user_text):
    with history_lock:
        if sender_id not in user_histories: user_histories[sender_id] = []
        history = user_histories[sender_id].copy()

    reply = None
    # Try Groq Keys
    for _ in range(min(3, len(GROQ_KEYS))):
        key, idx = get_next_key(GROQ_KEYS, groq_index)
        if key: 
            reply = try_groq(key, idx, history, user_text)
            if reply: break

    # Fallback to Gemini Keys
    if not reply:
        for _ in range(min(3, len(GEMINI_KEYS))):
            key, idx = get_next_key(GEMINI_KEYS, gemini_index)
            if key:
                reply = try_gemini(key, idx, history, user_text)
                if reply: break

    if not reply: return "নেটওয়ার্কে একটু সমস্যা করছে, পরে কথা বলি?"

    # Update History
    with history_lock:
        user_histories[sender_id].append({"role": "user", "parts": [{"text": user_text}]})
        user_histories[sender_id].append({"role": "model", "parts": [{"text": reply}]})
        if len(user_histories[sender_id]) > MAX_HISTORY * 2:
            user_histories[sender_id] = user_histories[sender_id][-20:]
    return reply

# --- Flask & Webhook Routes ---
@app.route("/")
def home(): return "Maya is Active!"

@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Verification Failed", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                if "message" in event and "text" in event["message"]:
                    sender_id = event["sender"]["id"]
                    user_text = event["message"]["text"]
                    threading.Thread(target=handle_message, args=(sender_id, user_text)).start()
    return "ok", 200

def handle_message(sender_id, user_text):
    reply = get_ai_response(sender_id, user_text)
    send_fb_message(sender_id, reply)

def send_fb_message(recipient_id, message_text):
    url = "https://graph.facebook.com/v18.0/me/messages"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {"recipient": {"id": recipient_id}, "message": {"text": message_text}}
    requests.post(url, params=params, json=data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
