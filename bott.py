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
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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


# ======================= کلاس دانلودر اینستاگرام =======================


class InstagramDownloader:

  TIMEOUT = 20

  def download(self, url):
    html_content = self._fetch_html(url)
    media = self._parse_json(html_content)
    if not media:
      media = self._parse_og_meta(html_content)
    if not media:
      raise Exception("Could not extract media from this post.")
    return media

  def _is_valid_url(self, url):
    pattern = (
        r"^https?://(www\.)?instagram\.com/(p|reel|tv)/[a-zA-Z0-9_-]+/?(\?.*)?"
    )
    return bool(re.match(pattern, url))

  def _fetch_html(self, url):
    headers = {
        "User-Agent": UA,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.5",
    }
    request = Request(url, headers=headers)
    try:
      with urlopen(request, timeout=self.TIMEOUT) as response:
        return response.read().decode("utf-8")
    except HTTPError as e:
      raise Exception(f"HTTP error: {e.code}")
    except URLError as e:
      raise Exception(f"Network error: {e.reason}")

  def _parse_json(self, html):
    match = re.search(
        r'__additionalDataLoaded\s*\(\s*["\'].*?["\']\s*,\s*(\{.*?\})\s*\)',
        html,
        re.DOTALL,
    )
    if match:
      try:
        data = json.loads(match.group(1))
        node = data.get("graphql", {}).get("shortcode_media", {})
        if node:
          return self._media_from_graphql_node(node)
      except Exception:
        pass

    match_ld = re.search(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if match_ld:
      try:
        data = json.loads(match_ld.group(1))
        if isinstance(data, list):
          data = data[0]
        video_url = data.get("video", [{}])
        if isinstance(video_url, list) and video_url:
          return {
              "type": "video",
              "url": video_url[0].get("contentUrl", ""),
              "thumbnail": data.get("thumbnailUrl", ""),
          }
        else:
          image = data.get("image")
          if image:
            return {
                "type": "image",
                "url": image if isinstance(image, str) else image[0],
            }
      except Exception:
        pass
    return None

  def _media_from_graphql_node(self, node):
    typename = node.get("__typename", "")
    if typename == "GraphVideo" or node.get("is_video"):
      video_url = node.get("video_url", "")
      if video_url:
        return {
            "type": "video",
            "url": video_url,
            "thumbnail": node.get("display_url")
            or node.get("thumbnail_src", ""),
        }
    else:
      image_url = node.get("display_url") or node.get("thumbnail_src", "")
      if image_url:
        return {"type": "image", "url": image_url}
    return None

  def _parse_og_meta(self, html):
    media = {}
    video_match = re.search(
        r'<meta\s+property=["\']og:video["\']\s+content=["\'](.*?)["\']',
        html,
        re.IGNORECASE,
    )
    if video_match:
      media["type"] = "video"
      media["url"] = unescape(video_match.group(1))
      thumb_match = re.search(
          r'<meta\s+property=["\']og:image["\']\s+content=["\'](.*?)["\']',
          html,
          re.IGNORECASE,
      )
      if thumb_match:
        media["thumbnail"] = unescape(thumb_match.group(1))
    else:
      image_match = re.search(
          r'<meta\s+property=["\']og:image["\']\s+content=["\'](.*?)["\']',
          html,
          re.IGNORECASE,
      )
      if image_match:
        media["type"] = "image"
        media["url"] = unescape(image_match.group(1))
    return media if media.get("url") else None


# ======================= دانلودر عمومی شبکه‌های اجتماعی =======================


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


# ---------- اینستاگرام با کلاس اختصاصی ----------
def instagram_custom_media(url, workdir):
  downloader = InstagramDownloader()
  media_info = downloader.download(url)
  m_url = media_info.get("url")
  m_type = "video" if media_info.get("type") == "video" else "photo"

  ext = ".mp4" if m_type == "video" else ".jpg"
  path = os.path.join(workdir, f"ig_media{ext}")
  download_file(m_url, path)
  return [(m_type, path)], None


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
  except Exception:
    pass

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
    except Exception:
      pass

  if not media:
    raise Exception("no media from twitter apis")

  items = []
  for i, (kind, murl) in enumerate(media[:10]):
    ext = ".jpg" if kind == "photo" else ".mp4"
    path = os.path.join(workdir, f"tw_{i}{ext}")
    download_file(murl, path)
    items.append((kind, path))
  return items, caption


# ---------- yt-dlp برای یوتیوب و سایرین ----------
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


def fetch_media(url, workdir):
  if "instagram.com" in url:
    steps = [instagram_custom_media, ytdlp_media]
  elif re.search(r"(?:twitter|x)\.com/", url):
    steps = [twitter_media, ytdlp_media]
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
        return items, caption
    except Exception as e:
      last_error = e
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
      except Exception:
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
  except Exception:
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
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"DOWNLOAD ERROR: {type(e).__name__}: {e}")

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
    print(f"CRITICAL ERROR: {e}")
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
