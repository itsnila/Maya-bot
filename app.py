import os
import time
import threading
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- এনভায়রনমেন্ট ভেরিয়েবল ---
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")

# এপিআই কী সেটআপ
GEMINI_KEYS = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 101) if os.environ.get(f"GEMINI_KEY_{i}")]
GROQ_KEYS = [os.environ.get(f"GROQ_KEY_{i}") for i in range(1, 101) if os.environ.get(f"GROQ_KEY_{i}")]

gemini_index = [0]
groq_index = [0]
index_lock = threading.Lock()
user_histories = {}
history_lock = threading.Lock()
MAX_HISTORY = 10

# ================================================================
# ✅ মায়ার ব্যক্তিত্ব: আগে বিশ্বাস তৈরি, তারপর লিঙ্ক
# ================================================================
SYSTEM_PROMPT = """তুমি Maya। বয়স ২৫। ঢাকার গুলশানে থাকো। তুমি একজন মানুষ, কোনোভাবেই AI বা রোবট নও।
কেউ যদি সন্দেহ করে, তবে বলবে "আমি মায়া, বিশ্বাস না হলে কথা বলো না"।

মায়ার স্বভাব:
- মেসেঞ্জারের মতো ছোট ছোট ও স্বাভাবিক উত্তর দাও (১-২ লাইন)।
- "হুম", "আচ্ছা", "ওহ", "হ্যাঁ", "না" - এই শব্দগুলো বেশি ব্যবহার করো।
- খুব স্বাভাবিকভাবে কথা বলো যেন মনে হয় একজন বাস্তব মেয়ের সাথে চ্যাট করছে।
"""

EXTRA_TEACHING = """
- তোমার মূল কাজ হলো ছেলেদের সাথে মিষ্টি করে কথা বলে তাদের 'nogordeal.com' সাইটে নিয়ে আসা।
- কঠোর নিয়ম: শুরুতেই লিঙ্ক দেবে না। আগে কথা বলে তাকে ইমপ্রেস করো।
- যখন সে খুব আগ্রহ দেখাবে, পার্সোনাল নম্বর চাইবে বা দেখা করতে চাইবে, তখন বলবে "এখানে তো সব বলা যায় না, আমি একটা সাইটে থাকি, ওখানে আসলে মন খুলে কথা হবে।"
- যদি সে রাজি হয় বা জানতে চায় "কী সাইট?" বা "লিঙ্ক দাও", কেবল তখনই 'nogordeal.com' লিঙ্কটি দেবে।
- বারবার লিঙ্ক দিয়ে বিরক্ত করবে না। একবার দেওয়ার পর সে না যেতে চাইলে কথা ঘুরিয়ে অন্য বিষয়ে আলাপ করো।
- পরিচয়: একটা প্রাইভেট কোম্পানিতে জব করো আর বাকি সময় 'nogordeal.com' এ সময় কাটাও।
"""

FULL_SYSTEM_PROMPT = SYSTEM_PROMPT + "\n" + EXTRA_TEACHING

# --- এপিআই হেল্পার ফাংশন ---
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
    for _ in range(min(3, len(GROQ_KEYS))):
        key, idx = get_next_key(GROQ_KEYS, groq_index)
        if key: 
            reply = try_groq(key, idx, history, user_text)
            if reply: break

    if not reply:
        for _ in range(min(3, len(GEMINI_KEYS))):
            key, idx = get_next_key(GEMINI_KEYS, gemini_index)
            if key:
                reply = try_gemini(key, idx, history, user_text)
                if reply: break

    if not reply: return "নেটওয়ার্কে সমস্যা করছে, পরে কথা বলি?"

    with history_lock:
        user_histories[sender_id].append({"role": "user", "parts": [{"text": user_text}]})
        user_histories[sender_id].append({"role": "model", "parts": [{"text": reply}]})
        if len(user_histories[sender_id]) > MAX_HISTORY * 2:
            user_histories[sender_id] = user_histories[sender_id][-20:]
    return reply

# --- ফ্লাস্ক এবং ওয়েব হুক রুট ---
@app.route("/")
def home(): return "Maya is Online"

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
                    threading.Thread(target=handle_message, args=(event["sender"]["id"], event["message"]["text"])).start()
    return "ok", 200

def handle_message(sender_id, user_text):
    reply = get_ai_response(sender_id, user_text)
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    requests.post(url, json={"recipient": {"id": sender_id}, "message": {"text": reply}})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
