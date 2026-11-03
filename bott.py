import json
import os
import sqlite3
import threading
import time
import requests
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity, ReactionTypeEmoji
import yt_dlp

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
    6420148931,
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

# راه‌اندازی دیتابیس
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


# ۱. هندلر استارت و قفل چنل
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


# ۲. دریافت فایل از ادمین برای ساخت لینک (فقط در چت خصوصی)
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


# هندلر هوشمند لینک‌های شبکه‌های اجتماعی (اینستاگرام، یوتیوب، توییتر)
@bot.message_handler(
    func=lambda message: message.text
    and any(
        domain in message.text
        for domain in [
            "instagram.com",
            "twitter.com",
            "x.com",
            "youtube.com",
            "youtu.be",
        ]
    )
)
def handle_social_links(message):
  url = message.text.strip()
  chat_id = message.chat.id
  message_id = message.message_id
  is_group = message.chat.type in ["group", "supergroup"]

  if is_group:
    try:
      bot.set_message_reaction(
          chat_id, message_id, [ReactionTypeEmoji("👀")]
      )
    except Exception:
      pass

  reply_to = message_id if is_group else None
  processing_msg = bot.send_message(
      chat_id,
      "⏳ در حال پردازش و دانلود رسانه...",
      reply_to_message_id=reply_to,
  )

  try:
    output_template = f"media_{chat_id}_{message_id}.%(ext)s"
    ydl_opts = {
        "outtmpl": output_template,
        "format": "best",
        "noplaylist": True,
        "socket_timeout": 30,
        "geo_bypass": True,
        "quiet": True,
        "no_warnings": True,
    }

    if "instagram.com" in url and os.path.exists("cookies.txt"):
      ydl_opts["cookiefile"] = "cookies.txt"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
      info = ydl.extract_info(url, download=True)
      filename = ydl.prepare_filename(info)
      original_caption = info.get("description", "کپشنی موجود نیست.")

    social_captions[filename] = original_caption

    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(
            "مشاهده کپشن 📋", callback_data=f"show_cap_{filename}"
        )
    )

    with open(filename, "rb") as f:
      if filename.endswith((".mp4", ".mkv", ".webm", ".mov")):
        bot.send_video(
            chat_id,
            f,
            caption="✨✨",
            reply_to_message_id=reply_to,
            reply_markup=markup,
        )
      elif filename.endswith((".jpg", ".jpeg", ".png", ".webp")):
        bot.send_photo(
            chat_id,
            f,
            caption="✨✨",
            reply_to_message_id=reply_to,
            reply_markup=markup,
        )
      else:
        bot.send_document(
            chat_id,
            f,
            caption="✨✨",
            reply_to_message_id=reply_to,
            reply_markup=markup,
        )

    if os.path.exists(filename):
      os.remove(filename)

    bot.delete_message(chat_id, processing_msg.message_id)

  except Exception as e:
    print(f"Error: {e}")
    try:
      bot.edit_message_text(
          "❌ دانلود از این لینک با خطا مواجه شد.",
          chat_id,
          processing_msg.message_id,
      )
    except:
      pass


# هندلر نمایش کپشن
@bot.callback_query_handler(func=lambda call: call.data.startswith("show_cap_"))
def callback_show_caption(call):
  filename_key = call.data.replace("show_cap_", "")
  caption = social_captions.get(
      filename_key, "کپشن این پست یافت نشد یا منقضی شده است."
  )
  bot.answer_callback_query(call.id, text=caption[:200], show_alert=True)


if __name__ == "__main__":
  print("Bot is running...")
  while True:
    try:
      bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception:
      time.sleep(3)
