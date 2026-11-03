import glob
import html
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import uuid

import requests
import telebot
import yt_dlp
from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    ReactionTypeEmoji,
)

# توکن ربات
TOKEN = "9032432816:AAEPZiX2VV2D5ppXpxsUUCAE7yJjn1swrTY"

ADMIN_IDS = [
    7904239647,
    1000843522,
    7856135158,
    5528031877,
    1251098392,
    6915992479,
    6573124305,
]

REQUIRED_CHANNELS = [
    {
        "id": "@Footy_Fuck",
        "url": "https://t.me/Footy_Fuck",
        "name": "عضویت در کانال اول 📢",
    },
    {
        "id": -1002568283880,
        "url": "https://t.me/+z_GCwt_dtc5mYzRk",
        "name": "عضویت در کانال دوم 📢",
    },
]

bot = telebot.TeleBot(TOKEN)

conn = sqlite3.connect("bot_data.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id TEXT,
        media_type TEXT,
        caption TEXT,
        entities TEXT
    )
""")
conn.commit()

pending_files = {}
social_captions = {}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.5"}

VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov", ".gif")
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".jfif")


def delete_messages(chat_id, *message_ids):
  for msg_id in message_ids:
    try:
      bot.delete_message(chat_id, msg_id)
    except Exception:
      pass


def check_membership(user_id):
  if user_id in ADMIN_IDS:
    return True
  for channel in REQUIRED_CHANNELS:
    try:
      status = bot.get_chat_member(channel["id"], user_id).status
      if status not in ["member", "administrator", "creator"]:
        return False
    except Exception:
      return False
  return True


# ۱. استارت و قفل چنل
@bot.message_handler(commands=["start"])
def start_command(message):
  text = message.text.split()
  payload = text[1] if len(text) > 1 else ""

  if not check_membership(message.from_user.id):
    markup = InlineKeyboardMarkup()
    for channel in REQUIRED_CHANNELS:
      markup.row(InlineKeyboardButton(channel["name"], url=channel["url"]))

    bot_info = bot.get_me()
    if payload.startswith("f_"):
      markup.row(
          InlineKeyboardButton(
              "عضو شدم، دریافت فایل 🔄",
              url=f"https://t.me/{bot_info.username}?start={payload}",
          )
      )
    else:
      markup.row(
          InlineKeyboardButton(
              "عضو شدم 🔄",
              url=f"https://t.me/{bot_info.username}?start=start",
          )
      )

    bot.reply_to(
        message,
        "⛔️ برای استفاده از ربات و دریافت فایل، ابتدا باید در کانال‌های زیر عضو"
        " شوید:",
        reply_markup=markup,
    )
    return

  if not payload or payload == "start":
    bot.reply_to(message, "به ربات خوش آمدید ✅")
    return

  if payload.startswith("f_"):
    try:
      file_db_id = int(payload.split("_")[1])
      cursor.execute(
          "SELECT file_id, media_type, caption, entities FROM files WHERE id"
          " = ?",
          (file_db_id,),
      )
      result = cursor.fetchone()

      if result:
        file_id, media_type, caption_text, entities_json = result
        sent_msg = None

        parsed_entities = None
        if entities_json:
          entities_list = json.loads(entities_json)
          parsed_entities = [
              telebot.types.MessageEntity(**e) for e in entities_list
          ]

        send_kwargs = {
            "chat_id": message.chat.id,
            "caption": caption_text,
            "caption_entities": parsed_entities,
        }

        if media_type == "doc":
          sent_msg = bot.send_document(document=file_id, **send_kwargs)
        elif media_type == "vid":
          sent_msg = bot.send_video(video=file_id, **send_kwargs)
        elif media_type == "aud":
          sent_msg = bot.send_audio(audio=file_id, **send_kwargs)
        elif media_type == "pho":
          sent_msg = bot.send_photo(photo=file_id, **send_kwargs)

        if sent_msg:
          warning_msg = bot.reply_to(
              sent_msg,
              "⚠️ این فایل تا 60 ثانیه دیگر پاک می‌شود. لطفاً آن را ذخیره کنید.",
          )
          timer = threading.Timer(
              60.0,
              delete_messages,
              args=(
                  message.chat.id,
                  sent_msg.message_id,
                  warning_msg.message_id,
              ),
          )
          timer.start()
      else:
        bot.reply_to(message, "❌ فایل مورد نظر یافت نشد.")
    except Exception:
      bot.reply_to(message, "❌ خطایی رخ داد.")


# ۲. دریافت فایل از ادمین
@bot.message_handler(content_types=["document", "video", "audio", "photo"])
def receive_file(message):
  if message.chat.type in ["group", "supergroup"]:
    return
  if message.from_user.id not in ADMIN_IDS:
    return

  file_id = None
  media_type = None

  if message.document:
    file_id = message.document.file_id
    media_type = "doc"
  elif message.video:
    file_id = message.video.file_id
    media_type = "vid"
  elif message.audio:
    file_id = message.audio.file_id
    media_type = "aud"
  elif message.photo:
    file_id = message.photo[-1].file_id
    media_type = "pho"

  if file_id and media_type:
    pending_files[message.chat.id] = {
        "file_id": file_id,
        "media_type": media_type,
    }
    msg = bot.reply_to(
        message,
        "✅ فایل دریافت شد.\n\n✍️ حالا لطفاً **کپشن** را بفرستید.\n🔸 اگر کپشن"
        " نمی‌خواهید دستور /skip را بفرستید.",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(msg, process_caption)


# ۳. دریافت کپشن و صدور لینک
def process_caption(message):
  if message.chat.id not in pending_files:
    return

  file_info = pending_files[message.chat.id]
  caption_text = None
  entities_json = None

  if message.text and message.text != "/skip":
    caption_text = message.text
    if message.entities:
      entities_list = []
      for ent in message.entities:
        ent_dict = {
            "type": ent.type,
            "offset": ent.offset,
            "length": ent.length,
            "url": ent.url,
            "custom_emoji_id": ent.custom_emoji_id,
        }
        ent_dict = {k: v for k, v in ent_dict.items() if v is not None}
        entities_list.append(ent_dict)
      entities_json = json.dumps(entities_list)

  cursor.execute(
      "INSERT INTO files (file_id, media_type, caption, entities) VALUES (?, ?,"
      " ?, ?)",
      (
          file_info["file_id"],
          file_info["media_type"],
          caption_text,
          entities_json,
      ),
  )
  conn.commit()
  short_id = cursor.lastrowid
  del pending_files[message.chat.id]

  bot_info = bot.get_me()
  link = f"https://t.me/{bot_info.username}?start=f_{short_id}"
  bot.reply_to(
      message,
      f"✅ فایل با موفقیت ثبت شد.\n\n🔗 لینک اختصاصی:\n`{link}`",
      parse_mode="Markdown",
  )


# ======================= دانلودر شبکه‌های اجتماعی =======================


def download_file(url, path, headers=None):
  with requests.get(
      url, headers=headers or HEADERS, stream=True, timeout=40
  ) as r:
    r.raise_for_status()
    with open(path, "wb") as f:
      for chunk in r.iter_content(chunk_size=65536):
        if chunk:
          f.write(chunk)


def collect_files(workdir):
  """فایل‌های دانلودشده را به صورت [(kind, path)] برمی‌گرداند."""
  items = []
  for p in sorted(glob.glob(os.path.join(workdir, "**", "*"), recursive=True)):
    if not os.path.isfile(p) or os.path.getsize(p) == 0:
      continue
    low = p.lower()
    if low.endswith(VIDEO_EXT):
      items.append(("video", p))
    elif low.endswith(IMAGE_EXT):
      items.append(("photo", p))
  return items[:10]


def ext_from_url(url, default):
  path = url.split("?")[0].lower()
  for e in IMAGE_EXT + VIDEO_EXT:
    if path.endswith(e):
      return e
  return default


# ---------- توییتر / X ----------
def twitter_media(url, workdir):
  m = re.search(r"(?:twitter|x)\.com/[^/]+/status(?:es)?/(\d+)", url)
  if not m:
    m = re.search(r"(?:twitter|x)\.com/i/(?:web/)?status/(\d+)", url)
  if not m:
    raise Exception("tweet id not found")
  tid = m.group(1)

  media = []
  caption = None

  # روش ۱: fxtwitter
  try:
    r = requests.get(
        f"https://api.fxtwitter.com/status/{tid}", headers=HEADERS, timeout=20
    )
    data = r.json().get("tweet") or {}
    caption = data.get("text")
    md = data.get("media") or {}
    for it in md.get("all") or []:
      kind = "photo" if it.get("type") == "photo" else "video"
      if it.get("url"):
        media.append((kind, it["url"]))
    if not media:
      for it in md.get("photos") or []:
        media.append(("photo", it["url"]))
      for it in md.get("videos") or []:
        media.append(("video", it["url"]))
  except Exception as e:
    print("fxtwitter failed:", e)

  # روش ۲: vxtwitter
  if not media:
    try:
      r = requests.get(
          f"https://api.vxtwitter.com/Twitter/status/{tid}",
          headers=HEADERS,
          timeout=20,
      )
      data = r.json()
      caption = caption or data.get("text")
      for it in data.get("media_extended") or []:
        kind = "photo" if it.get("type") == "image" else "video"
        if it.get("url"):
          media.append((kind, it["url"]))
    except Exception as e:
      print("vxtwitter failed:", e)

  if not media:
    raise Exception("no media from twitter apis")

  items = []
  for i, (kind, murl) in enumerate(media[:10]):
    ext = ext_from_url(murl, ".jpg" if kind == "photo" else ".mp4")
    path = os.path.join(workdir, f"tw_{i}{ext}")
    download_file(murl, path)
    items.append((kind, path))
  return items, caption


# ---------- yt-dlp ----------
def ytdlp_media(url, workdir):
  opts = {
      "noplaylist": True,
      "quiet": True,
      "no_warnings": True,
      "outtmpl": os.path.join(workdir, "%(id)s_%(autonumber)s.%(ext)s"),
      "format": "best[ext=mp4][filesize<50M]/best[ext=mp4]/best",
      "merge_output_format": "mp4",
      "http_headers": HEADERS,
  }
  if "instagram.com" in url and os.path.exists("cookies.txt"):
    opts["cookiefile"] = "cookies.txt"

  with yt_dlp.YoutubeDL(opts) as ydl:
    info = ydl.extract_info(url, download=True)
  if info and "entries" in info:
    entries = [e for e in info["entries"] if e]
    info = entries[0] if entries else info
  caption = info.get("description") if info else None

  items = collect_files(workdir)
  if not items:
    raise Exception("yt-dlp downloaded nothing")
  return items, caption


# ---------- gallery-dl (مخصوص عکس) ----------
def gallerydl_media(url, workdir):
  cmd = ["gallery-dl", "-D", workdir, "--no-mtime"]
  if os.path.exists("cookies.txt"):
    cmd += ["--cookies", "cookies.txt"]
  cmd.append(url)
  p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
  items = collect_files(workdir)
  if not items:
    raise Exception(f"gallery-dl failed: {p.stderr[-200:]}")
  return items, None


# ---------- اینستاگرام embed (بدون لاگین، برای پست‌های عمومی) ----------
def instagram_embed_media(url, workdir):
  m = re.search(
      r"instagram\.com/(?:[^/]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)", url
  )
  if not m:
    raise Exception("instagram shortcode not found")
  code = m.group(1)
  r = requests.get(
      f"https://www.instagram.com/p/{code}/embed/captioned/",
      headers=HEADERS,
      timeout=20,
  )
  r.raise_for_status()
  imgs = re.findall(r'class="EmbeddedMediaImage"[^>]*src="([^"]+)"', r.text)
  if not imgs:
    imgs = re.findall(r'src="([^"]+)"[^>]*class="EmbeddedMediaImage"', r.text)
  if not imgs:
    raise Exception("no image in embed page")

  items = []
  for i, img in enumerate(imgs[:10]):
    img = html.unescape(img)
    path = os.path.join(workdir, f"ig_{i}.jpg")
    download_file(img, path)
    items.append(("photo", path))

  caption = None
  cm = re.search(r'class="Caption"[^>]*>(.*?)</div>', r.text, re.S)
  if cm:
    caption = html.unescape(re.sub(r"<[^>]+>", " ", cm.group(1))).strip()
  return items, caption


def fetch_media(url, workdir):
  """چند روش را به ترتیب امتحان می‌کند تا یکی جواب بدهد."""
  if re.search(r"(?:twitter|x)\.com/", url):
    steps = [twitter_media, ytdlp_media, gallerydl_media]
  elif "instagram.com" in url:
    steps = [ytdlp_media, gallerydl_media, instagram_embed_media]
  else:
    steps = [ytdlp_media]

  last_error = None
  for step in steps:
    try:
      for f in glob.glob(os.path.join(workdir, "*")):
        if os.path.isfile(f):
          os.remove(f)
      items, caption = step(url, workdir)
      if items:
        print(f"OK via {step.__name__}")
        return items, caption
    except Exception as e:
      last_error = e
      print(f"{step.__name__} failed: {e}")
  raise Exception(last_error or "all methods failed")


def send_items(chat_id, items, reply_to, markup):
  def send_single(kind, path, mk):
    with open(path, "rb") as f:
      try:
        if kind == "video":
          return bot.send_video(
              chat_id,
              f,
              caption="✨✨",
              reply_to_message_id=reply_to,
              reply_markup=mk,
              timeout=120,
          )
        return bot.send_photo(
            chat_id,
            f,
            caption="✨✨",
            reply_to_message_id=reply_to,
            reply_markup=mk,
            timeout=120,
        )
      except Exception as e:
        print("send failed, trying as document:", e)
        f.seek(0)
        return bot.send_document(
            chat_id,
            f,
            caption="✨✨",
            reply_to_message_id=reply_to,
            reply_markup=mk,
            timeout=120,
        )

  if len(items) == 1:
    send_single(items[0][0], items[0][1], markup)
    return

  # آلبوم
  handles = []
  try:
    media = []
    for i, (kind, path) in enumerate(items):
      fh = open(path, "rb")
      handles.append(fh)
      cls = InputMediaVideo if kind == "video" else InputMediaPhoto
      media.append(cls(fh, caption="✨✨" if i == 0 else None))
    sent = bot.send_media_group(chat_id, media, reply_to_message_id=reply_to)
    bot.send_message(
        chat_id,
        "📋",
        reply_to_message_id=sent[0].message_id,
        reply_markup=markup,
    )
  except Exception as e:
    print("media group failed, sending one by one:", e)
    for kind, path in items:
      send_single(kind, path, None)
    bot.send_message(chat_id, "📋", reply_markup=markup)
  finally:
    for fh in handles:
      fh.close()


SOCIAL_DOMAINS = [
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "youtu.be",
]


@bot.message_handler(
    func=lambda m: m.text and any(d in m.text for d in SOCIAL_DOMAINS)
)
def handle_social_links(message):
  m = re.search(r"https?://\S+", message.text)
  if not m:
    return
  url = m.group(0).strip()
  if "instagram.com" in url:
    url = url.split("?")[0]

  chat_id = message.chat.id
  message_id = message.message_id
  is_group = message.chat.type in ["group", "supergroup"]
  reply_to = message_id if is_group else None

  if is_group:
    try:
      bot.set_message_reaction(chat_id, message_id, [ReactionTypeEmoji("👀")])
    except Exception:
      pass

  processing_msg = bot.send_message(
      chat_id,
      "⏳ در حال پردازش و استخراج رسانه...",
      reply_to_message_id=reply_to,
  )

  workdir = tempfile.mkdtemp(prefix="dl_")
  try:
    items, caption = fetch_media(url, workdir)

    key = uuid.uuid4().hex[:12]
    social_captions[key] = caption or "کپشنی موجود نیست."
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("مشاهده کپشن 📋", callback_data=f"cap_{key}")
    )

    send_items(chat_id, items, reply_to, markup)
    delete_messages(chat_id, processing_msg.message_id)

  except Exception as e:
    print(f"CRITICAL ERROR in handle_social_links: {e}")
    try:
      bot.edit_message_text(
          "❌ دانلود از این لینک انجام نشد. (پست خصوصی است یا حذف شده)",
          chat_id,
          processing_msg.message_id,
      )
    except Exception:
      pass
  finally:
    shutil.rmtree(workdir, ignore_errors=True)


@bot.callback_query_handler(func=lambda call: call.data.startswith("cap_"))
def callback_show_caption(call):
  key = call.data[4:]
  caption = social_captions.get(key, "کپشن این پست یافت نشد یا منقضی شده است.")
  bot.answer_callback_query(call.id, text=caption[:200], show_alert=True)


if __name__ == "__main__":
  print("Bot is running...")
  while True:
    try:
      bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception:
      time.sleep(3)
