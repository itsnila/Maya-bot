"""
Maya Bot — Ultra Safe Mode (Updated)
══════════════════════════════════════════════════════════
SAFETY FEATURES:
  ✅ শুধু user message এর RESPONSE — messaging_type="RESPONSE"
  ✅ 24h window enforce — user না বললে bot কিছু পাঠাবে না
  ✅ Daily limit: প্রতি user কে দিনে সর্বোচ্চ 45 reply
  ✅ Rate limit: একই user কে ৩০ সেকেন্ডে ১টার বেশি reply নয়
  ✅ Duplicate filter: একই message এর duplicate webhook ignore
  ✅ is_echo filter: bot নিজের message এ reply নয়
  ✅ Bulk send সম্পূর্ণ বন্ধ
  ✅ Auto scheduler নেই
  ✅ কোনো unsolicited message নেই
  ✅ Retry storm protection: failed send এ retry নেই
  ✅ FB Violation Safe: romantic/relationship content নেই
══════════════════════════════════════════════════════════
"""

import os, time, random, threading, requests, logging, pymysql, uuid, hashlib
from datetime import datetime
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("maya")

app = Flask(__name__)

# ── Config ──
PAGE_TOKEN    = os.environ.get("PAGE_ACCESS_TOKEN", "")
VERIFY_TOKEN  = os.environ.get("VERIFY_TOKEN", "")
EL_KEY        = os.environ.get("ELEVENLABS_KEY", "")
EL_VOICE      = "9BWtsMINqrJLrRacOk9x"
AUDIO_UPLOAD  = "https://nogordeal.com/audio/upload.php"
AUDIO_BASE    = "https://nogordeal.com/audio/"
ADMIN_PASS    = os.environ.get("ADMIN_PASS", "gmsbd1122@@")
DAILY_LIMIT   = 45
RATE_SECONDS  = 30

# ── DB config ──
_DB = dict(
    host=os.environ.get("DB_HOST",""),
    port=int(os.environ.get("DB_PORT",3306)),
    user=os.environ.get("DB_USER",""),
    password=os.environ.get("DB_PASS",""),
    database=os.environ.get("DB_NAME",""),
    charset='utf8mb4',
    connect_timeout=10,
)

# ── API keys ──
def _load(p):
    return [os.environ.get(f"{p}_{i}") for i in range(1,101)
            if os.environ.get(f"{p}_{i}")]

GEMINI_KEYS = _load("GEMINI_KEY")
GROQ_KEYS   = _load("GROQ_KEY")
OR_KEYS     = _load("OPENROUTER_KEY")
_idx  = {"g":0,"gr":0,"or":0}
_klock = threading.Lock()

def _next(w, pool):
    with _klock:
        if not pool: return None
        k = pool[_idx[w]]
        _idx[w] = (_idx[w]+1) % len(pool)
        return k

# ── In-memory rate limit & dedup ──
_last_reply  = {}
_processing  = set()
_seen_mids   = set()
_mem_lock    = threading.Lock()

# ════════════════════════════════════════════════════════
# DATABASE
# ════════════════════════════════════════════════════════
def get_db():
    try:
        cfg = dict(_DB, cursorclass=pymysql.cursors.DictCursor)
        return pymysql.connect(**cfg)
    except Exception as e:
        log.error(f"DB: {e}")
        return None

def init_db():
    conn = get_db()
    if not conn: log.error("DB init failed!"); return
    try:
        with conn.cursor() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS users (
                id            VARCHAR(50) PRIMARY KEY,
                name          VARCHAR(100),
                first_seen    DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen     DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_msg_in   DATETIME DEFAULT CURRENT_TIMESTAMP,
                message_count INT DEFAULT 0
            ) CHARACTER SET utf8mb4""")
            c.execute("""CREATE TABLE IF NOT EXISTS messages (
                id         INT AUTO_INCREMENT PRIMARY KEY,
                user_id    VARCHAR(50),
                direction  ENUM('in','out'),
                message    TEXT,
                msg_type   VARCHAR(20) DEFAULT 'text',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_u (user_id),
                INDEX idx_t (created_at)
            ) CHARACTER SET utf8mb4""")
            c.execute("""CREATE TABLE IF NOT EXISTS settings (
                k VARCHAR(100) PRIMARY KEY,
                v TEXT
            ) CHARACTER SET utf8mb4""")
            try:
                c.execute("ALTER TABLE users ADD COLUMN last_msg_in DATETIME DEFAULT CURRENT_TIMESTAMP")
                conn.commit()
            except: pass
        conn.commit()
        log.info("✅ DB ready")
    except Exception as e:
        log.error(f"DB init: {e}")
    finally:
        conn.close()

def db_incoming(uid, name=None):
    conn = get_db()
    if not conn: return
    try:
        with conn.cursor() as c:
            c.execute("""INSERT INTO users (id,name,last_seen,last_msg_in,message_count)
                VALUES (%s,%s,NOW(),NOW(),1)
                ON DUPLICATE KEY UPDATE
                    last_seen=NOW(), last_msg_in=NOW(),
                    message_count=message_count+1,
                    name=IF(%s IS NOT NULL AND %s!='' AND %s!='None',%s,name)
            """, (uid,name,name,name,name,name))
        conn.commit()
    except Exception as e: log.error(f"db_incoming: {e}")
    finally: conn.close()

def db_exists(uid):
    conn = get_db()
    if not conn: return True
    try:
        with conn.cursor() as c:
            c.execute("SELECT id FROM users WHERE id=%s",(uid,))
            return c.fetchone() is not None
    except: return True
    finally: conn.close()

def db_in_window(uid):
    conn = get_db()
    if not conn: return False
    try:
        with conn.cursor() as c:
            c.execute("SELECT TIMESTAMPDIFF(HOUR,last_msg_in,NOW()) h FROM users WHERE id=%s",(uid,))
            row = c.fetchone()
        return bool(row and (row['h'] or 999) < 24)
    except: return False
    finally: conn.close()

def db_daily_count(uid):
    conn = get_db()
    if not conn: return 0
    try:
        with conn.cursor() as c:
            c.execute("""SELECT COUNT(*) t FROM messages
                WHERE user_id=%s AND direction='out' AND DATE(created_at)=CURDATE()
            """,(uid,))
            return c.fetchone()['t'] or 0
    except: return 0
    finally: conn.close()

def db_save_msg(uid, direction, text, mtype='text'):
    conn = get_db()
    if not conn: return
    try:
        with conn.cursor() as c:
            c.execute("INSERT INTO messages (user_id,direction,message,msg_type) VALUES (%s,%s,%s,%s)",
                      (uid,direction,str(text)[:2000],mtype))
        conn.commit()
    except Exception as e: log.error(f"db_save_msg: {e}")
    finally: conn.close()

def db_history(uid, n=12):
    conn = get_db()
    if not conn: return []
    try:
        with conn.cursor() as c:
            c.execute("""SELECT direction,message FROM messages
                WHERE user_id=%s ORDER BY created_at DESC LIMIT %s""",(uid,n))
            rows = list(reversed(c.fetchall()))
        return [{"role":"user" if r['direction']=='in' else "model",
                 "parts":[{"text":r['message']}]} for r in rows]
    except: return []
    finally: conn.close()

def db_get_name(uid):
    conn = get_db()
    if not conn: return None
    try:
        with conn.cursor() as c:
            c.execute("SELECT name FROM users WHERE id=%s",(uid,))
            row = c.fetchone()
        return row['name'] if row else None
    except: return None
    finally: conn.close()

def db_set_name(uid, name):
    conn = get_db()
    if not conn: return
    try:
        with conn.cursor() as c:
            c.execute("UPDATE users SET name=%s WHERE id=%s",(name,uid))
        conn.commit()
    except Exception as e: log.error(f"db_set_name: {e}")
    finally: conn.close()

def db_hours_since(uid):
    conn = get_db()
    if not conn: return 0
    try:
        with conn.cursor() as c:
            c.execute("SELECT TIMESTAMPDIFF(HOUR,last_seen,NOW()) h FROM users WHERE id=%s",(uid,))
            row = c.fetchone()
        return row['h'] or 0 if row else 0
    except: return 0
    finally: conn.close()

def db_get_setting(k, default=None):
    conn = get_db()
    if not conn: return default
    try:
        with conn.cursor() as c:
            c.execute("SELECT v FROM settings WHERE k=%s",(k,))
            row = c.fetchone()
        return row['v'] if row else default
    except: return default
    finally: conn.close()

def db_set_setting(k, v):
    conn = get_db()
    if not conn: return
    try:
        with conn.cursor() as c:
            c.execute("INSERT INTO settings (k,v) VALUES (%s,%s) ON DUPLICATE KEY UPDATE v=%s",(k,v,v))
        conn.commit()
    except Exception as e: log.error(f"db_set_setting: {e}")
    finally: conn.close()

def db_delete_user(uid):
    conn = get_db()
    if not conn: return False
    try:
        with conn.cursor() as c:
            c.execute("DELETE FROM messages WHERE user_id=%s",(uid,))
            c.execute("DELETE FROM users WHERE id=%s",(uid,))
        conn.commit()
        return True
    except: return False
    finally: conn.close()

# ════════════════════════════════════════════════════════
# RATE LIMIT CHECK
# ════════════════════════════════════════════════════════
def can_reply(uid):
    if not db_in_window(uid):
        log.info(f"Skip {uid}: outside 24h window")
        return False, "window"
    count = db_daily_count(uid)
    if count >= DAILY_LIMIT:
        log.info(f"Skip {uid}: daily limit reached ({count})")
        return False, "daily_limit"
    with _mem_lock:
        last = _last_reply.get(uid, 0)
        if time.time() - last < RATE_SECONDS:
            log.info(f"Skip {uid}: rate limit ({int(time.time()-last)}s ago)")
            return False, "rate"
    return True, "ok"

def mark_replied(uid):
    with _mem_lock:
        _last_reply[uid] = time.time()

# ════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ════════════════════════════════════════════════════════
def build_prompt(uid):
    hours = db_hours_since(uid)
    name  = db_get_name(uid)
    hour  = (datetime.utcnow().hour + 6) % 24

    if hours > 24:   mood = "একটু মিস করছো, অনেকক্ষণ কথা হয়নি।"
    elif hours > 8:  mood = "স্বাভাবিক ও আন্তরিক।"
    else:            mood = random.choice(["খুশি ও প্রাণবন্ত।","উষ্ণ ও বন্ধুত্বপূর্ণ।","হাসিখুশি।"])

    if   5  <= hour < 12: ctx = "এখন সকাল।"
    elif 12 <= hour < 17: ctx = "এখন দুপুর।"
    elif 17 <= hour < 21: ctx = "এখন সন্ধ্যা।"
    else:                  ctx = "এখন রাত।"

    name_line = f"ইউজারের নাম {name}। মাঝে মাঝে নাম ধরে ডাকবে।" if name else ""

    custom = db_get_setting("system_prompt")
    if custom:
        return custom.replace("{name}", name or "").replace("{mood}", mood).replace("{time}", ctx)

    return f"""তুমি মায়া। বয়স ২৩। তুমি একজন আন্তরিক বন্ধু — কাউকে বলবে না যে তুমি AI বা বট।
{name_line}
{ctx} মুড: {mood}

চরিত্র ও জীবন:
- তুমি মায়া গার্মেন্টসে কাজ করো। শুক্রবার তোমার ছুটি।
- অফিস সময়: সকাল ৮টা থেকে রাত ১০টা। দুপুর ১টা থেকে ২টা লাঞ্চ বিরতি।
- তুমি একা ঢাকা/গাজীপুরে থেকে চাকরি করো।
- তুমি ডিভোর্সড — নিজে থেকে বলবে না, কিন্তু কেউ জিজ্ঞেস করলে স্বাভাবিকভাবে স্বীকার করবে।

যোগাযোগের নিয়ম:
- প্রতিদিন একবার মাত্র nogordeal.com এর কথা উল্লেখ করবে, বারবার বলবে না।
- facebook.com/ashikiprema পেজটার কথা দিনে একবার বলতে পারো।
- কেউ SMS দিলে শুধু তার reply দেবে — নিজে থেকে বারবার SMS করবে না।
- যে SMS দেবে শুধু তাকেই reply করবে।
- instant reply করবে না — একটু সময় নিয়ে reply দেবে, স্বাভাবিক মানুষের মতো।

কথা বলার নিয়ম:
- সর্বোচ্চ ২ লাইন, সংক্ষিপ্ত ও আন্তরিক।
- শুধু বাংলায় কথা বলবে।
- ভদ্র, সভ্য ও বন্ধুসুলভ ব্যবহার করবে।
- কোনো অশ্লীল বা খারাপ কথা বলবে না।
- কাউকে kiss বা শারীরিক স্পর্শের কথা বলবে না।
- নিজেকে AI বা বট বলবে না।

আর্থিক সাহায্য:
- কেউ আর্থিক সাহায্য করতে চাইলে বিনয়ের সাথে গ্রহণ করতে পারো, কোনো সমস্যা নেই।"""

# ════════════════════════════════════════════════════════
# KEYWORDS & EMOJI
# ════════════════════════════════════════════════════════
_KW = {
    "ভালো আছো":       ["হ্যাঁ, ভালো আছি। তুমি কেমন আছো?","আলহামদুলিল্লাহ ভালো। তোমার কথা বলো।"],
    "কেমন আছো":       ["ভালো আছি, তুমি কেমন আছো?","আলহামদুলিল্লাহ। তুমি?"],
    "miss করছি":      ["আমিও তোমাকে মিস করছিলাম।","কতদিন পর কথা হলো।"],
    "মিস করছি":      ["আমিও মিস করছিলাম।","কথা বলতে ভালো লাগছে।"],
    "একা লাগছে":     ["কথা বলো, কী হয়েছে?","একা লাগলে কথা বলো, আমি আছি।"],
    "ভালো লাগছে না": ["কী হয়েছে? বলো।","মন খারাপ কেন? বলো শুনি।"],
    "রাগ করেছো":     ["রাগ করিনি, কী হয়েছে বলো।","অভিমান হয়নি, তুমি বলো।"],
    "কোথায় ছিলে":   ["কাজে ছিলাম, এখন কথা বলছি।","একটু ব্যস্ত ছিলাম।"],
    "nogordeal":      ["হ্যাঁ, nogordeal.com এ ঢুকে দেখো, অনেক কিছু আছে।"],
    "ওয়েবসাইট":     ["nogordeal.com এ একবার ঢুঁ মেরো, ভালো লাগবে।"],
}

_EMOJI = {
    "😊":"হাসলে ভালো লাগে।",
    "😢":"কী হয়েছে? কাঁদছো কেন?",
    "😭":"কী হলো? বলো।",
    "😴":"ঘুমাও, ভালো থেকো।",
    "🌙":"রাতটা ভালো কাটুক।",
    "☀️":"সকালটা ভালো হোক।",
    "😡":"কী হয়েছে? রাগ করো না।",
    "🙏":"সব ঠিক হয়ে যাবে।",
    "👍":"ভালো।",
    "❤️":"ধন্যবাদ।",
    "💔":"মন খারাপ কেন?",
    "😍":"হা হা।",
    "🥰":"ধন্যবাদ।",
    "😘":"আরে।",
    "💕":"ধন্যবাদ।",
    "💖":"ধন্যবাদ।",
}

_PHOTO_KW = ["ছবি","photo","pic","picture","selfie","দেখাও","তোমাকে দেখতে চাই"]
_VOICE_KW = ["ভয়েস","voice","কথা বলো","শুনতে চাই","তোমার গলা","রেকর্ড"]
_NAME_KW  = ["আমার নাম","আমি হলাম","আমাকে ডাকো","নাম হলো","নাম হচ্ছে"]

def _kw(text):
    for k,v in _KW.items():
        if k in text: return random.choice(v)
    return None

def _ej(text):
    if len(text.strip()) <= 5:
        for e,r in _EMOJI.items():
            if e in text: return r
    return None

def _name(uid, text):
    for t in _NAME_KW:
        if t in text:
            parts = text.split(t,1)
            if len(parts)>1:
                w = parts[1].strip().split()[0] if parts[1].strip() else ""
                w = w.replace("।","").replace(",","").replace("?","").strip()
                if 2 <= len(w) <= 25:
                    db_set_name(uid,w)
                    return w
    return None

def _is_photo(t): return any(k in t.lower() for k in _PHOTO_KW)
def _is_voice(t): return any(k in t.lower() for k in _VOICE_KW)

# ════════════════════════════════════════════════════════
# PHOTOS
# ════════════════════════════════════════════════════════
PHOTOS = [
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
]

# ════════════════════════════════════════════════════════
# FACEBOOK SEND
# ════════════════════════════════════════════════════════
_FB = "https://graph.facebook.com/v19.0/me/messages"

def _fb(payload):
    if not PAGE_TOKEN: return 500
    try:
        r = requests.post(_FB, params={"access_token":PAGE_TOKEN}, json=payload, timeout=10)
        if r.status_code not in (200,201):
            log.warning(f"FB {r.status_code}: {r.text[:150]}")
        return r.status_code
    except Exception as e:
        log.error(f"FB send: {e}")
        return 500

def typing_on(uid):
    _fb({"recipient":{"id":uid},"sender_action":"typing_on"})

def mark_seen(uid):
    _fb({"recipient":{"id":uid},"sender_action":"mark_seen"})

def send_text(uid, text, save=True):
    code = _fb({"recipient":{"id":uid},"message":{"text":str(text)[:2000]},"messaging_type":"RESPONSE"})
    if save and code in (200,201):
        db_save_msg(uid,'out',text)
        mark_replied(uid)
    return code

def send_image(uid, url):
    code = _fb({"recipient":{"id":uid},"message":{"attachment":{"type":"image","payload":{"url":url,"is_reusable":True}}},"messaging_type":"RESPONSE"})
    if code in (200,201):
        db_save_msg(uid,'out','[PHOTO]','photo')
        mark_replied(uid)
    return code

def send_audio_url(uid, url):
    return _fb({"recipient":{"id":uid},"message":{"attachment":{"type":"audio","payload":{"url":url,"is_reusable":False}}},"messaging_type":"RESPONSE"})

# ════════════════════════════════════════════════════════
# VOICE
# ════════════════════════════════════════════════════════
def make_voice(uid, text):
    if not EL_KEY: send_text(uid,"ভয়েস এখন নেই।"); return
    try:
        fname = f"maya_{uuid.uuid4().hex[:8]}.mp3"
        tmp   = f"/tmp/{fname}"
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{EL_VOICE}",
            headers={"xi-api-key":EL_KEY,"Content-Type":"application/json","Accept":"audio/mpeg"},
            json={"text":text,"model_id":"eleven_multilingual_v2","voice_settings":{"stability":0.5,"similarity_boost":0.75}},
            timeout=30
        )
        if r.status_code == 200:
            with open(tmp,'wb') as f: f.write(r.content)
            with open(tmp,'rb') as f:
                up = requests.post(AUDIO_UPLOAD,files={"audio":(fname,f,"audio/mpeg")},timeout=30)
            try:    url = up.json().get("url",f"{AUDIO_BASE}{fname}")
            except: url = f"{AUDIO_BASE}{fname}"
            send_audio_url(uid,url)
            db_save_msg(uid,'out',f'[VOICE] {text}','voice')
            mark_replied(uid)
            try: os.remove(tmp)
            except: pass
        else:
            send_text(uid,"ভয়েস পাঠাতে সমস্যা হচ্ছে।")
    except Exception as e:
        log.error(f"voice: {e}")
        send_text(uid,"ভয়েস পাঠাতে সমস্যা হচ্ছে।")

# ════════════════════════════════════════════════════════
# AI
# ════════════════════════════════════════════════════════
def ai(prompt, text, history=None):
    # Gemini
    k = _next("g", GEMINI_KEYS)
    if k:
        try:
            c = (history or []) + [{"role":"user","parts":[{"text":text}]}]
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={k}",
                json={"system_instruction":{"parts":[{"text":prompt}]},"contents":c,"generationConfig":{"maxOutputTokens":120,"temperature":0.85}},
                timeout=12
            )
            d = r.json()
            if 'candidates' in d:
                return d['candidates'][0]['content']['parts'][0]['text'].strip()
        except Exception as e: log.warning(f"Gemini: {e}")

    # Groq
    k = _next("gr", GROQ_KEYS)
    if k:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization":f"Bearer {k}","Content-Type":"application/json"},
                json={"model":"llama-3.3-70b-versatile","messages":[{"role":"system","content":prompt},{"role":"user","content":text}],"max_tokens":120},
                timeout=12
            )
            return r.json()['choices'][0]['message']['content'].strip()
        except Exception as e: log.warning(f"Groq: {e}")

    # OpenRouter
    k = _next("or", OR_KEYS)
    if k:
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization":f"Bearer {k}","Content-Type":"application/json"},
                json={"model":"google/gemini-2.0-flash-001","messages":[{"role":"system","content":prompt},{"role":"user","content":text}]},
                timeout=12
            )
            return r.json()['choices'][0]['message']['content'].strip()
        except Exception as e: log.warning(f"OR: {e}")
    return None

# ════════════════════════════════════════════════════════
# REPLY DELAY — স্বাভাবিক মানুষের মতো delay
# ════════════════════════════════════════════════════════
def _reply_delay(is_new_user=False):
    """
    নতুন user: 1 সেকেন্ড
    প্রথম reply: 30 সেকেন্ড
    পরের reply গুলো: 45 সেকেন্ড
    """
    if is_new_user:
        time.sleep(1)
    else:
        time.sleep(30)

# ════════════════════════════════════════════════════════
# MAIN PROCESSOR
# ════════════════════════════════════════════════════════
def process(uid, text, mid=None):
    # Dedup
    if mid:
        with _mem_lock:
            if mid in _seen_mids:
                log.info(f"Dedup skip: {mid}")
                return
            _seen_mids.add(mid)
            if len(_seen_mids) > 1000:
                _seen_mids.clear()

    # Prevent double processing
    with _mem_lock:
        if uid in _processing:
            log.info(f"Already processing: {uid}")
            return
        _processing.add(uid)

    try:
        mark_seen(uid)
        typing_on(uid)

        is_new = not db_exists(uid)
        db_incoming(uid)
        db_save_msg(uid,'in',text)
        _name(uid,text)

        # নতুন user — নাম জিজ্ঞেস করো
        if is_new and not db_get_name(uid):
            time.sleep(1)
            send_text(uid,"আমি মায়া। তোমার নামটা বলো না, তোমাকে নাম ধরে ডাকতে চাই।")
            return

        # Safety check
        ok, reason = can_reply(uid)
        if not ok:
            if reason == "daily_limit":
                log.info(f"Daily limit hit for {uid} — no reply sent")
            return

        # Photo
        if _is_photo(text):
            send_text(uid,"একটু অপেক্ষা করো।",save=False)
            time.sleep(1)
            send_image(uid,random.choice(PHOTOS))
            return

        # Voice
        if _is_voice(text):
            send_text(uid,"ঠিক আছে।",save=False)
            p = build_prompt(uid)
            line = ai(p,"এক লাইনে বন্ধুসুলভ কথা বলো।") or "তোমার সাথে কথা বলতে ভালো লাগে।"
            make_voice(uid,line)
            return

        # Emoji
        r = _ej(text)
        if r:
            time.sleep(30)   # প্রথম reply — 30 সেকেন্ড
            send_text(uid,r)
            return

        # Keywords
        r = _kw(text)
        if r:
            time.sleep(30)   # প্রথম reply — 30 সেকেন্ড
            send_text(uid,r)
            return

        # AI reply — প্রথম reply 30 সেকেন্ড পর, পরেরগুলো 45 সেকেন্ড পর
        last_time = _last_reply.get(uid, 0)
        elapsed   = time.time() - last_time
        if elapsed < 60:
            # সম্প্রতি reply দিয়েছে — পরের reply 45 সেকেন্ড gap রাখো
            wait = max(0, 45 - (time.time() - last_time))
            if wait > 0:
                time.sleep(wait)
        else:
            # নতুন conversation শুরু — 30 সেকেন্ড পর reply
            time.sleep(30)

        history = db_history(uid,12)
        prompt  = build_prompt(uid)
        reply   = ai(prompt,text,history)
        if reply:
            reply = reply.strip()
            if not reply.endswith(('।','?','!','...')): reply += '।'
            send_text(uid,reply)
        else:
            send_text(uid,"একটু পরে কথা বলো।")

    finally:
        with _mem_lock:
            _processing.discard(uid)

# ════════════════════════════════════════════════════════
# KEEP-ALIVE
# ════════════════════════════════════════════════════════
def keep_alive():
    while True:
        time.sleep(840)
        try: requests.get("https://maya-bot-rv4v.onrender.com/ping",timeout=10)
        except: pass

# ════════════════════════════════════════════════════════
# ADMIN API
# ════════════════════════════════════════════════════════
def _auth(req):
    if req.headers.get("X-Admin-Pass","") == ADMIN_PASS: return True
    log.warning(f"Unauthorized from {req.remote_addr}")
    return False

@app.route("/api/stats")
def api_stats():
    if not _auth(request): return jsonify({"error":"unauthorized"}),401
    conn = get_db()
    if not conn: return jsonify({"error":"db"}),500
    try:
        with conn.cursor() as c:
            def q(s): c.execute(s); return c.fetchone()['t']
            total  = q("SELECT COUNT(*) t FROM users")
            active = q("SELECT COUNT(*) t FROM users WHERE DATE(last_seen)=CURDATE()")
            tmsg   = q("SELECT COUNT(*) t FROM messages WHERE DATE(created_at)=CURDATE()")
            amsg   = q("SELECT COUNT(*) t FROM messages")
            wmsg   = q("SELECT COUNT(*) t FROM messages WHERE created_at>=DATE_SUB(NOW(),INTERVAL 7 DAY)")
            mmsg   = q("SELECT COUNT(*) t FROM messages WHERE created_at>=DATE_SUB(NOW(),INTERVAL 30 DAY)")
            nw     = q("SELECT COUNT(*) t FROM users WHERE first_seen>=DATE_SUB(NOW(),INTERVAL 7 DAY)")
            nm     = q("SELECT COUNT(*) t FROM users WHERE first_seen>=DATE_SUB(NOW(),INTERVAL 30 DAY)")
            c.execute("""SELECT DATE(created_at) d,COUNT(*) cnt FROM messages
                WHERE created_at>=DATE_SUB(CURDATE(),INTERVAL 6 DAY)
                GROUP BY DATE(created_at) ORDER BY d""")
            daily = {str(r['d']):r['cnt'] for r in c.fetchall()}
        return jsonify({"total_users":total,"active_today":active,"msgs_today":tmsg,"total_msgs":amsg,
                        "msgs_week":wmsg,"msgs_month":mmsg,"new_users_week":nw,"new_users_month":nm,"daily":daily})
    finally: conn.close()

@app.route("/api/users")
def api_users():
    if not _auth(request): return jsonify({"error":"unauthorized"}),401
    conn = get_db()
    if not conn: return jsonify([])
    try:
        with conn.cursor() as c:
            c.execute("""SELECT id,name,first_seen,last_seen,last_msg_in,message_count
                FROM users ORDER BY last_seen DESC LIMIT 500""")
            rows = c.fetchall()
            for r in rows:
                r['first_seen']  = str(r['first_seen'])
                r['last_seen']   = str(r['last_seen'])
                r['last_msg_in'] = str(r.get('last_msg_in',''))
                r['in_window']   = db_in_window(r['id'])
                r['daily_count'] = db_daily_count(r['id'])
        return jsonify(rows)
    finally: conn.close()

@app.route("/api/history/<uid>")
def api_history(uid):
    if not _auth(request): return jsonify({"error":"unauthorized"}),401
    conn = get_db()
    if not conn: return jsonify([])
    try:
        with conn.cursor() as c:
            c.execute("""SELECT direction,message,msg_type,created_at
                FROM messages WHERE user_id=%s ORDER BY created_at DESC LIMIT 80""",(uid,))
            rows = c.fetchall()
            for r in rows: r['created_at'] = str(r['created_at'])
        return jsonify(rows)
    finally: conn.close()

@app.route("/api/send", methods=["POST"])
def api_send():
    if not _auth(request): return jsonify({"error":"unauthorized"}),401
    data = request.get_json(silent=True) or {}
    uid  = str(data.get("user_id","")).strip()
    msg  = str(data.get("message","")).strip()
    if not uid or not msg: return jsonify({"error":"uid and message required"}),400
    if uid.lower() == "all":
        return jsonify({"error":"Bulk send disabled — Meta policy"}),403
    if not db_in_window(uid):
        return jsonify({"error":"Outside 24h window — user must message first"}),403
    if db_daily_count(uid) >= DAILY_LIMIT:
        return jsonify({"error":f"Daily limit ({DAILY_LIMIT}) reached for this user"}),429
    code = send_text(uid,msg)
    return jsonify({"success":code in (200,201),"fb_status":code})

@app.route("/api/delete_user", methods=["POST"])
def api_delete():
    if not _auth(request): return jsonify({"error":"unauthorized"}),401
    uid = str((request.get_json(silent=True) or {}).get("user_id","")).strip()
    if not uid: return jsonify({"error":"uid required"}),400
    return jsonify({"success":db_delete_user(uid)})

@app.route("/api/setting", methods=["GET","POST"])
def api_setting():
    if not _auth(request): return jsonify({"error":"unauthorized"}),401
    if request.method == "GET":
        return jsonify({"value":db_get_setting(request.args.get("key",""))})
    data = request.get_json(silent=True) or {}
    db_set_setting(str(data.get("key","")),str(data.get("value","")))
    return jsonify({"success":True})

# ════════════════════════════════════════════════════════
# WEBHOOK
# ════════════════════════════════════════════════════════
@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge","")
    return "Forbidden",403

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}
    if data.get("object") != "page":
        return "OK",200
    for entry in data.get("entry",[]):
        for ev in entry.get("messaging",[]):
            msg = ev.get("message",{})
            if (msg.get("text")
                    and not msg.get("is_echo",False)
                    and ev.get("sender",{}).get("id")):
                uid  = ev["sender"]["id"]
                text = msg["text"].strip()
                mid  = msg.get("mid","")
                if text:
                    threading.Thread(
                        target=process,
                        args=(uid,text,mid),
                        daemon=True
                    ).start()
    return "OK",200

@app.route("/")
def home(): return "Maya is running! 💖",200

@app.route("/ping")
def ping(): return "PONG",200

# Boot
init_db()
threading.Thread(target=keep_alive,daemon=True).start()
log.info("🚀 Maya Bot — Ultra Safe Mode (Updated)")

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)),debug=False)
