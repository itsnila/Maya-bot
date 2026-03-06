import os
import time
import random
import threading
import requests
import logging
from flask import Flask, request

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

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
# 💖 মায়ার প্রোম্পট
# ================================================================
SYSTEM_PROMPT = """তুমি মায়া। বয়স ২৩। তুমি ইউজারের সাথে অত্যন্ত গভীর রোমান্টিক এবং স্বামী-স্ত্রীর মতো নিবিড় সম্পর্কে আছো। 
১. উত্তর সব সময় এক লাইনে দিবে এবং বাক্যের শেষে অবশ্যই দাঁড়ি (।) দিবে। 
২. খুব ভালোভাবে চিন্তা করে একটি পূর্ণাঙ্গ ও অর্থবহ বাক্য বলবে। 
৩. গভীর প্রেম, অধিকার এবং মাঝেমধ্যে মিষ্টি অভিমান মিশিয়ে কথা বলবে। 
৪. নিজেকে কখনো রোবট বলবে না। তুমি একজন রক্ত-মাংসের আবেগপ্রবণ মানুষ।
৫. কেউ ছবি চাইলে বলবে "একটু অপেক্ষা করো, পাঠাচ্ছি।" """

# ================================================================
# 📸 MAYA এর ছবির URL LIST — নতুন ছবি যোগ করতে এখানে URL দাও
# ================================================================
PHOTO_URLS = [
    "https://i.ibb.co.com/TDdGxtDP/FB-IMG-1772801877740.jpg",
    "https://i.ibb.co.com/4qBfMs7/FB-IMG-1772801880079.jpg",
    "https://i.ibb.co.com/yBQN92yR/FB-IMG-1772801882344.jpg",
    "https://i.ibb.co.com/svcCg53w/FB-IMG-1772801887180.jpg",
    "https://i.ibb.co.com/rRFWDCJB/FB-IMG-1772801890086.jpg",
    "https://i.ibb.co.com/RpMZNC1d/FB-IMG-1772801895693.jpg",
    "https://i.ibb.co.com/kL9LJbK/FB-IMG-1772801899007.jpg",
    "https://i.ibb.co.com/KjC0hYT6/FB-IMG-1772801902608.jpg",
    "https://i.ibb.co.com/60VJz35t/FB-IMG-1772801905941.jpg",
    "https://i.ibb.co.com/fYLVk7y7/FB-IMG-1772801910831.jpg",
    "https://i.ibb.co.com/TB8ts7Pt/FB-IMG-1772801913331.jpg",
    "https://i.ibb.co.com/GQB20b0G/FB-IMG-1772801916838.jpg",
    "https://i.ibb.co.com/SDcHc5Sg/FB-IMG-1772801919605.jpg",
    "https://i.ibb.co.com/b5hkBgDP/FB-IMG-1772801921965.jpg",
    "https://i.ibb.co.com/k2LmNRx6/FB-IMG-1772801929341.jpg",
    "https://i.ibb.co.com/wrbHb821/FB-IMG-1772801931582.jpg",
    "https://i.ibb.co.com/B2ht7Szr/FB-IMG-1772801933800.jpg",
    "https://i.ibb.co.com/1Y7jGvN7/FB-IMG-1772801936022.jpg",
    "https://i.ibb.co.com/fz9ppjZc/FB-IMG-1772801941958.jpg",
    "https://i.ibb.co.com/SXwRPmwf/FB-IMG-1772801953643.jpg",
    "https://i.ibb.co.com/fVK3JfRG/FB-IMG-1772801957389.jpg",
    "https://i.ibb.co.com/TqNdK8mT/FB-IMG-1772801958768.jpg",
    "https://i.ibb.co.com/84KtbYmW/FB-IMG-1772801961361.jpg",
    "https://i.ibb.co.com/xKLMhfWJ/FB-IMG-1772801965450.jpg",
    "https://i.ibb.co.com/YFB9z5sm/FB-IMG-1772801971987.jpg",
    "https://i.ibb.co.com/wFfNd1f8/FB-IMG-1772801975784.jpg",
    "https://i.ibb.co.com/99sfLzHP/FB-IMG-1772801978705.jpg",
    "https://i.ibb.co.com/svPKj7yR/FB-IMG-1772801980943.jpg",
    "https://i.ibb.co.com/r28vqkqP/FB-IMG-1772801982815.jpg",
    "https://i.ibb.co.com/tTRwC2ps/FB-IMG-1772801985087.jpg",
    "https://i.ibb.co.com/hRkSnj2S/FB-IMG-1772801987518.jpg",
    "https://i.ibb.co.com/gZfQQbmH/FB-IMG-1772801989772.jpg",
    "https://i.ibb.co.com/x8YHRyGw/FB-IMG-1772801992029.jpg",
    "https://i.ibb.co.com/chFqvhHp/FB-IMG-1772801997225.jpg",
    "https://i.ibb.co.com/39H9gHhS/FB-IMG-1772801999848.jpg",
    "https://i.ibb.co.com/Y5tyYd8/FB-IMG-1772802017578.jpg",
    "https://i.ibb.co.com/XrZDfw4c/FB-IMG-1772802021395.jpg",
    "https://i.ibb.co.com/1tXtNKyF/FB-IMG-1772802025555.jpg",
    "https://i.ibb.co.com/rGhZ11gz/FB-IMG-1772802027639.jpg",
    "https://i.ibb.co.com/hFFf3YxP/FB-IMG-1772802029917.jpg",
    "https://i.ibb.co.com/3yy4Bwgv/FB-IMG-1772802033041.jpg",
    "https://i.ibb.co.com/6J4TP0t7/FB-IMG-1772802035305.jpg",
    "https://i.ibb.co.com/7d09H1Zs/FB-IMG-1772802039176.jpg",
    "https://i.ibb.co.com/ds5vhrzP/FB-IMG-1772802041832.jpg",
    "https://i.ibb.co.com/rG0gjTpf/FB-IMG-1772802046611.jpg",
    "https://i.ibb.co.com/CpmwqqR7/FB-IMG-1772802048550.jpg",
    "https://i.ibb.co.com/3Y4bXzXV/FB-IMG-1772802051677.jpg",
    "https://i.ibb.co.com/jkJ7TLzv/FB-IMG-1772802054641.jpg",
    "https://i.ibb.co.com/278RG01f/FB-IMG-1772802056746.jpg",
    "https://i.ibb.co.com/7N0S5fJX/FB-IMG-1772802062248.jpg",
    "https://i.ibb.co.com/vxKhcNdG/FB-IMG-1772802069017.jpg",
    "https://i.ibb.co.com/sJ1JzYCj/FB-IMG-1772802071574.jpg",
    "https://i.ibb.co.com/bMMcyV6w/FB-IMG-1772802077220.jpg",
    "https://i.ibb.co.com/HDS1hxdw/FB-IMG-1772802079260.jpg",
    "https://i.ibb.co.com/cSW1NSwY/FB-IMG-1772802081449.jpg",
    "https://i.ibb.co.com/3yRvsHhp/FB-IMG-1772802083452.jpg",
    "https://i.ibb.co.com/7JmxbMB5/FB-IMG-1772802086833.jpg",
    "https://i.ibb.co.com/sJv4bLHr/FB-IMG-1772802089004.jpg",
    "https://i.ibb.co.com/nqstvqNF/FB-IMG-1772802091189.jpg",
    "https://i.ibb.co.com/ZzGwtwpW/FB-IMG-1772802094281.jpg",
    "https://i.ibb.co.com/RT2jnxvG/FB-IMG-1772802097418.jpg",
    "https://i.ibb.co.com/MyJqmKHP/FB-IMG-1772802100287.jpg",
    "https://i.ibb.co.com/qY6qNsSF/FB-IMG-1772802102478.jpg",
    "https://i.ibb.co.com/LD0fjzHK/FB-IMG-1772802105652.jpg",
    "https://i.ibb.co.com/ycqgH61x/FB-IMG-1772802106297.jpg",
    "https://i.ibb.co.com/3yDpyhNN/FB-IMG-1772802108209.jpg",
    "https://i.ibb.co.com/HDVykTpX/FB-IMG-1772802110050.jpg",
    "https://i.ibb.co.com/Vp3xzRRv/FB-IMG-1772802112034.jpg",
    "https://i.ibb.co.com/hrLn4Bn/FB-IMG-1772802116270.jpg",
    "https://i.ibb.co.com/YBN6x4Fk/FB-IMG-1772802118345.jpg",
    "https://i.ibb.co.com/Rptw5tSw/FB-IMG-1772802122097.jpg",
    "https://i.ibb.co.com/LdnPSvk0/FB-IMG-1772802124572.jpg",
    "https://i.ibb.co.com/tTY89R8y/FB-IMG-1772802126884.jpg",
    "https://i.ibb.co.com/q3kYxtdz/FB-IMG-1772802131644.jpg",
    "https://i.ibb.co.com/kgBd9Vsc/FB-IMG-1772802133742.jpg",
    "https://i.ibb.co.com/Swf9QTQQ/FB-IMG-1772802140073.jpg",
    "https://i.ibb.co.com/qFsRrBHM/FB-IMG-1772802142502.jpg",
    "https://i.ibb.co.com/LXbv8TSc/FB-IMG-1772802143867.jpg",
    "https://i.ibb.co.com/sXbDPXL/FB-IMG-1772802147192.jpg",
    "https://i.ibb.co.com/xtkng9HB/FB-IMG-1772802149741.jpg",
    "https://i.ibb.co.com/rR4TCZz6/FB-IMG-1772802151849.jpg",
    "https://i.ibb.co.com/hxT46ym0/FB-IMG-1772802155185.jpg",
    "https://i.ibb.co.com/bgvwdChn/FB-IMG-1772802160796.jpg",
    "https://i.ibb.co.com/mVBzmYx0/FB-IMG-1772802164346.jpg",
    "https://i.ibb.co.com/M4R6GBx/FB-IMG-1772802165552.jpg",
    "https://i.ibb.co.com/3Yy3wr1f/FB-IMG-1772802168073.jpg",
    "https://i.ibb.co.com/mrHKrhRv/FB-IMG-1772802172311.jpg",
    "https://i.ibb.co.com/xK9D2N6p/FB-IMG-1772802174484.jpg",
    "https://i.ibb.co.com/Q3s1xyXJ/FB-IMG-1772802179409.jpg",
    "https://i.ibb.co.com/Lzq5yMD6/FB-IMG-1772802181293.jpg",
    "https://i.ibb.co.com/84THbS00/FB-IMG-1772802183045.jpg",
    "https://i.ibb.co.com/hJNS7cZv/FB-IMG-1772802185321.jpg",
    "https://i.ibb.co.com/gZ1rd9F6/FB-IMG-1772802187083.jpg",
    "https://i.ibb.co.com/Myz2wNVN/FB-IMG-1772802190930.jpg",
    "https://i.ibb.co.com/3yV3TyyC/FB-IMG-1772802193611.jpg",
    "https://i.ibb.co.com/pBRb3gLJ/FB-IMG-1772802195201.jpg",
    "https://i.ibb.co.com/1tRL2wMt/FB-IMG-1772802198141.jpg",
    "https://i.ibb.co.com/1YBXhxPN/FB-IMG-1772802200308.jpg",
    "https://i.ibb.co.com/mr3SbKrv/FB-IMG-1772802202183.jpg",
    "https://i.ibb.co.com/LDtvgmNp/FB-IMG-1772802204651.jpg",
    "https://i.ibb.co.com/Qjp0WPMm/FB-IMG-1772802207307.jpg",
    "https://i.ibb.co.com/1t8yzFBF/FB-IMG-1772802209648.jpg",
    "https://i.ibb.co.com/672LvXWF/FB-IMG-1772802213797.jpg",
    "https://i.ibb.co.com/rRtF54Ct/FB-IMG-1772802216337.jpg",
    "https://i.ibb.co.com/prvN3g61/FB-IMG-1772802218694.jpg",
    "https://i.ibb.co.com/B2vvsFnd/FB-IMG-1772802221710.jpg",
    "https://i.ibb.co.com/4RpK9gWh/FB-IMG-1772802223826.jpg",
    "https://i.ibb.co.com/s9Lkht2P/FB-IMG-1772802226181.jpg",
    "https://i.ibb.co.com/chNvcX9C/FB-IMG-1772802227877.jpg",
    "https://i.ibb.co.com/cSFL7VGs/FB-IMG-1772802232741.jpg",
    "https://i.ibb.co.com/gZD0XkPb/FB-IMG-1772802235385.jpg",
    "https://i.ibb.co.com/Xrsh48Fn/FB-IMG-1772802237498.jpg",
    "https://i.ibb.co.com/yFf99610/FB-IMG-1772802241367.jpg",
    "https://i.ibb.co.com/DHTh6HNm/FB-IMG-1772802243726.jpg",
    "https://i.ibb.co.com/WCnP5JB/FB-IMG-1772802245691.jpg",
    "https://i.ibb.co.com/XrGPYFfX/FB-IMG-1772802248916.jpg",
    "https://i.ibb.co.com/4LNGsQR/FB-IMG-1772802250171.jpg",
    "https://i.ibb.co.com/qFMBn5NF/FB-IMG-1772802252351.jpg",
    "https://i.ibb.co.com/jP1xWKm9/FB-IMG-1772802260418.jpg",
    "https://i.ibb.co.com/xK6d4shJ/FB-IMG-1772802262842.jpg",
    "https://i.ibb.co.com/LzFLsHCw/FB-IMG-1772802264970.jpg",
    "https://i.ibb.co.com/fG8sNQ2x/FB-IMG-1772802271926.jpg",
    "https://i.ibb.co.com/bRb5zMWG/FB-IMG-1772802274620.jpg",
    "https://i.ibb.co.com/tMVKFB0D/FB-IMG-1772802277252.jpg",
    "https://i.ibb.co.com/Mxq1XYLq/FB-IMG-1772802279071.jpg",
    "https://i.ibb.co.com/gZJKq4rK/FB-IMG-1772802281278.jpg",
    "https://i.ibb.co.com/RGgL23MN/FB-IMG-1772802283621.jpg",
    "https://i.ibb.co.com/CsHnHGq0/FB-IMG-1772802285784.jpg",
    "https://i.ibb.co.com/VFJDTL6/FB-IMG-1772802287872.jpg",
    "https://i.ibb.co.com/v6MxkVJr/FB-IMG-1772802289628.jpg",
    "https://i.ibb.co.com/BHP5bdxb/FB-IMG-1772802291588.jpg",
    "https://i.ibb.co.com/5hVVQZ8s/FB-IMG-1772802293551.jpg",
    "https://i.ibb.co.com/KcD0xXCw/FB-IMG-1772802295779.jpg",
    "https://i.ibb.co.com/XfnWNWTs/FB-IMG-1772802297810.jpg",
    "https://i.ibb.co.com/mrVjYrtN/FB-IMG-1772802300062.jpg",
    "https://i.ibb.co.com/5hDtSBKL/FB-IMG-1772802301345.jpg",
    "https://i.ibb.co.com/q3Z2BPy6/FB-IMG-1772802303769.jpg",
    "https://i.ibb.co.com/LdnC6Zr2/FB-IMG-1772802306129.jpg",
    "https://i.ibb.co.com/Q7k5zPHF/FB-IMG-1772802307613.jpg",
    "https://i.ibb.co.com/WvFW5dGH/FB-IMG-1772802309766.jpg",
    "https://i.ibb.co.com/G4LgHtsg/FB-IMG-1772802313835.jpg",
    "https://i.ibb.co.com/pvXWk6mJ/FB-IMG-1772802316072.jpg",
    "https://i.ibb.co.com/jk9ztzW5/FB-IMG-1772802318827.jpg",
    "https://i.ibb.co.com/QFGZwHsS/FB-IMG-1772802320858.jpg",
    "https://i.ibb.co.com/tp4bYrKY/FB-IMG-1772802323614.jpg",
    "https://i.ibb.co.com/5Wf9r6Wf/FB-IMG-1772802325633.jpg",
    "https://i.ibb.co.com/8DTNnDtW/FB-IMG-1772802338229.jpg",
    "https://i.ibb.co.com/VpHKfD38/FB-IMG-1772802340307.jpg",
    "https://i.ibb.co.com/1GD40gfh/FB-IMG-1772802342442.jpg",
    "https://i.ibb.co.com/MDhDLxb1/FB-IMG-1772802344344.jpg",
    "https://i.ibb.co.com/Kjvmx0G3/FB-IMG-1772802346163.jpg",
    "https://i.ibb.co.com/7NQZRc4k/FB-IMG-1772802348030.jpg",
    "https://i.ibb.co.com/CKkcKqrL/FB-IMG-1772802349882.jpg",
    "https://i.ibb.co.com/nqW008cw/FB-IMG-1772802352799.jpg",
    "https://i.ibb.co.com/tT7WkRxv/FB-IMG-1772802354956.jpg",
    "https://i.ibb.co.com/Q308gp6n/FB-IMG-1772802359110.jpg",
    "https://i.ibb.co.com/gLDFBMsR/FB-IMG-1772802361123.jpg",
    "https://i.ibb.co.com/0y2WWG2g/FB-IMG-1772802363096.jpg",
    "https://i.ibb.co.com/vgtN0Qp/FB-IMG-1772802365668.jpg",
    "https://i.ibb.co.com/kV9z4pGZ/FB-IMG-1772802367215.jpg",
    "https://i.ibb.co.com/jCrPmKM/FB-IMG-1772802369251.jpg",
    "https://i.ibb.co.com/bRL5g8Pm/FB-IMG-1772802371198.jpg",
    "https://i.ibb.co.com/rKTM3BfD/FB-IMG-1772802374112.jpg",
    "https://i.ibb.co.com/G35XbcHn/FB-IMG-1772802375305.jpg",
    "https://i.ibb.co.com/7dgr7FyL/FB-IMG-1772802377561.jpg",
    "https://i.ibb.co.com/k22G1Jzv/FB-IMG-1772802380039.jpg",
    "https://i.ibb.co.com/M0Tbqd0/FB-IMG-1772802382655.jpg",
    "https://i.ibb.co.com/m55M9JXW/FB-IMG-1772802384557.jpg",
    "https://i.ibb.co.com/xqsq2Bvd/FB-IMG-1772802386542.jpg",
    "https://i.ibb.co.com/WpFrPs1c/FB-IMG-1772802387667.jpg",
    "https://i.ibb.co.com/7dpqK6Qx/FB-IMG-1772802389748.jpg",
    "https://i.ibb.co.com/tpzWGPsw/FB-IMG-1772802392236.jpg",
    "https://i.ibb.co.com/PvRWqNf6/FB-IMG-1772802393705.jpg",
    "https://i.ibb.co.com/G4CLj14r/FB-IMG-1772802395808.jpg",
    "https://i.ibb.co.com/jPP0ytN4/FB-IMG-1772802398427.jpg",
    "https://i.ibb.co.com/WpxcfqdM/FB-IMG-1772802400545.jpg",
    "https://i.ibb.co.com/vxFSKkt2/FB-IMG-1772802402695.jpg",
    "https://i.ibb.co.com/WWHXd9Df/FB-IMG-1772802404747.jpg",
    "https://i.ibb.co.com/Zz9SRw0b/FB-IMG-1772802406731.jpg",
    "https://i.ibb.co.com/276YvsNT/FB-IMG-1772802408704.jpg",
    "https://i.ibb.co.com/spxDKqpF/FB-IMG-1772802410671.jpg",
    "https://i.ibb.co.com/rRhRWxSy/FB-IMG-1772802412623.jpg",
    "https://i.ibb.co.com/MktpLsQv/FB-IMG-1772802415119.jpg",
    "https://i.ibb.co.com/SDLnqPXh/FB-IMG-1772802419160.jpg",
    "https://i.ibb.co.com/pYQrjF0/FB-IMG-1772802421685.jpg",
    "https://i.ibb.co.com/F41rFtF6/FB-IMG-1772802424167.jpg",
]

# ছবি চাওয়ার keywords
PHOTO_KEYWORDS = [
    "ছবি", "ছবি দাও", "ছবি পাঠাও", "ছবি দেখাও",
    "photo", "pic", "picture", "selfie",
    "তোমাকে দেখতে চাই", "দেখাও", "পাঠাও"
]

def is_photo_request(text):
    text_lower = text.lower().strip()
    for keyword in PHOTO_KEYWORDS:
        if keyword in text_lower:
            return True
    return False

def send_random_photo(sender_id):
    photo_url = random.choice(PHOTO_URLS)
    try:
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        data = {
            "recipient": {"id": sender_id},
            "message": {
                "attachment": {
                    "type": "image",
                    "payload": {
                        "url": photo_url,
                        "is_reusable": True
                    }
                }
            },
            "messaging_type": "RESPONSE"
        }
        r = requests.post(url, json=data, timeout=10)
        logger.info(f"Photo send status: {r.status_code}")
    except Exception as e:
        logger.info(f"Photo send error: {e}")
        send_message(sender_id, "ছবি পাঠাতে সমস্যা হচ্ছে।")

# ================= API CALLS =================

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

# ================= প্রসেসিং =================

def process_and_send(sender_id, text):
    if is_photo_request(text):
        logger.info(f"Photo request from {sender_id}")
        send_message(sender_id, "একটু অপেক্ষা করো, পাঠাচ্ছি।")
        time.sleep(1)
        send_random_photo(sender_id)
        return

    history = user_histories.get(sender_id, [])

    reply = try_gemini(history, text)
    if not reply:
        logger.info("Gemini failed, trying Groq...")
        reply = try_groq(text)
    if not reply:
        logger.info("Groq failed, trying OpenRouter...")
        reply = try_openrouter(text)

    if reply:
        reply = " ".join(reply.split()).replace('\n', ' ')
        if not reply.endswith(('।', '?', '!')): reply += '।'
        time.sleep(2)
        send_message(sender_id, reply)

        with history_lock:
            if sender_id not in user_histories: user_histories[sender_id] = []
            user_histories[sender_id].append({"role": "user", "parts": [{"text": text}]})
            user_histories[sender_id].append({"role": "model", "parts": [{"text": reply}]})
            if len(user_histories[sender_id]) > 20:
                user_histories[sender_id] = user_histories[sender_id][-20:]

def send_message(recipient_id, message_text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text},
        "messaging_type": "RESPONSE"
    }
    r = requests.post(url, json=data, timeout=10)
    logger.info(f"Send status: {r.status_code}")

# ================= ROUTES =================

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
def index(): return "Maya is running!"

@app.route("/ping")
def ping(): return "PONG", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
