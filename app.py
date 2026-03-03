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

# Environment Variables (Set these in your hosting panel)
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")

def load_keys(prefix):
    keys = []
    for i in range(1, 101):
        key = os.environ.get(f"{prefix}_{i}")
        if key: keys.append(key)
    return keys

# Loading all keys
GEMINI_KEYS = load_keys("GEMINI_KEY")
GROQ_KEYS = load_keys("GROQ_KEY")
OPENROUTER_KEYS = load_keys("OPENROUTER_KEY")

# Global Indexes for Load Balancing
gemini_index = 0
groq_index = 0
openrouter_index = 0
index_lock = threading.Lock()

user_histories = {}
history_lock = threading.Lock()
MAX_HISTORY = 6 # Jate Maya to the point kotha bole

# ================================================================
# ✅ MAYA-ER CHARACTER TRAINING (PROMPT)
# ================================================================
SYSTEM_PROMPT = """Tumi Maya. Boyos 25. Dhaka, Gulshan-e thako. Tumi ekjon manush, kono AI ba robot nou.

Tor kotha bolar dhoron:
- Khub kom kotha bolo. Messenger-e manush jemon choto kore reply dey temon (Ex: Hum, hobe, thik ache, keno?).
- Uttor shob shomoy 1 line-e rakhar chesta korbe. Maximum 2 line.
- Tumi shobar sathe khub bhalo ebong affectionate bhabe kotha bolo.
- **Probashider Proti Agroho:** Keu jodi bole shey desh-er baire thake, tahole bolbe "Bah, onek kosto koren apnara. Nijer kheyal rakhen kintu."
- **Number Policy:** Keu mobile number ba personal ID chaile bolbe "Etoi taratari? Age bondhu hoye dekhi" ba "Ekhon na, pore kono ekdin hobe".
- Shuddho ebong cholito banglar mishron-e kotha bolo (Messenger language).
- Robot-er moto list ba boro kotha bolbe na.
"""

# ================= HELPER FUNCTIONS =================

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

# ================= API IMPLEMENTATIONS =================

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
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "HTTP-Referer": "https://render.com"}
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

# ================= MAIN LOGIC =================

def get_ai_response(sender_id, user_text):
    history = user_histories.get(sender_id, [])
    
    # Cascade: Groq -> OpenRouter -> Gemini
    reply = try_groq(history, user_text)
    if not reply:
        logger.info("Groq failed, trying OpenRouter...")
        reply = try_openrouter(history, user_text)
    if not reply:
        logger.info("OpenRouter failed, trying Gemini...")
        reply = try_gemini(history, user_text)
    
    if reply:
        update_history(sender_id, "user", user_text)
        update_history(sender_id, "assistant", reply)
        return reply
    return "Um.. ki bolbo thik bujhte parchi na."

# ================= WEBHOOKS =================

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
def index(): return "Maya is Live"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
