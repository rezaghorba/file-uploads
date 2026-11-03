import asyncio
import os
import re
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ContentType
from aiogram.filters import Command
from aiogram.types import FSInputFile, ReactionTypeEmoji
import yt_dlp

# توکن بات (همان توکن اصلی ربات شما)
TOKEN = '9032432816:AAEPZiX2VV2D5ppXpxsUUCAE7yJjn1swrTY'

bot = Bot(token=TOKEN)
dp = Dispatcher()

# رجکس برای تشخیص لینک‌های توییتر (ایکس)
TWITTER_REGEX = re.compile(
    r'https?://(?:www\.)?(?:twitter\.com|x\.com)/\w+/status/\d+'
)


def download_media(tweet_url):
  """تابع دانلود ویدیو یا تصویر از توییتر با yt-dlp"""
  output_dir = 'downloads'
  os.makedirs(output_dir, exist_ok=True)

  ydl_opts = {
      'outtmpl': os.path.join(output_dir, '%(id)s.%(ext)s'),
      'format': 'best[ext=mp4]/best',
      'quiet': True,
      'no_warnings': True,
  }

  try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
      info = ydl.extract_info(tweet_url, download=True)
      filename = ydl.prepare_filename(info)

      # بررسی وجود فایل
      if os.path.exists(filename):
        return filename, 'video'

      # اگر ویدیوی مستقیم نبود، شاید تصویر باشد
      # در صورت وجود فرمت‌های تصویری
      return filename, 'media'
  except Exception as e:
    print(f'Download Error: {e}')
    return None, None


@dp.message(F.text & ~F.text.startswith('/'))
async def handle_twitter_links(message: types.Message):
  text = message.text

  # پیدا کردن لینک توییت در متن پیام
  match = TWITTER_REGEX.search(text)
  if not match:
    return  # اگر لینک توییتر نبود، ربات کاری انجام ندهد (تا با بقیه کدهای شما تداخل نکند)

  tweet_url = match.group(0)

  # ۱. گذاشتن ری‌اکشن چشم 👀 روی پیام کاربر (چه در پی‌وی و چه در گروه)
  try:
    await bot.set_message_reaction(
        chat_id=message.chat.id,
        message_id=message.message_id,
        reaction=[ReactionTypeEmoji(emoji='👀')],
    )
  except Exception as e:
    print(f'Reaction Error (Might not be supported in some chats): {e}')

  # اطلاع‌رسانی موقت یا پردازش
  processing_msg = None
  try:
    processing_msg = await message.reply(
        '⏳ در حال دریافت و دانلود مدیا از توییتر...'
    )
  except:
    pass

  # ۲. دانلود رسانه
  file_path, media_type = await asyncio.to_thread(download_media, tweet_url)

  if not file_path or not os.path.exists(file_path):
    if processing_msg:
      try:
        await processing_msg.edit_text(
            '❌ متأسفانه دانلود ویدیو/مدیا از این توییت امکان‌پذیر نبود.'
        )
      except:
        pass
    return

  # ۳. ارسال فایل به کاربر / گروه با ریپلای روی پیام اصلی
  try:
    input_file = FSInputFile(file_path)

    # تشخیص اینکه ویدیو است یا عکس/فایل
    if file_path.endswith(('.mp4', '.mkv', '.webm', '.mov')):
      await message.reply_video(
          video=input_file, caption='📥 دانلود شده توسط بات'
      )
    else:
      await message.reply_document(
          document=input_file, caption='📥 دانلود شده توسط بات'
      )

    # پاک کردن پیام موقتِ در حال دانلود
    if processing_msg:
      await processing_msg.delete()

  except Exception as e:
    print(f'Telegram Send Error: {e}')
    if processing_msg:
      try:
        await processing_msg.edit_text(f'❌ خطا در ارسال فایل: {e}')
      except:
        pass

  finally:
    # پاکسازی فایل دانلود شده از هاست برای جلوگیری از پر شدن حافظه رندر
    if file_path and os.path.exists(file_path):
      try:
        os.remove(file_path)
      except:
        pass


async def main():
  print('Twitter Bot is running...')
  # پاک کردن وب‌هوک‌های قبلی برای جلوگیری از ارور Conflict
  await bot.delete_webhook(drop_pending_updates=True)
  await dp.start_polling(bot)


import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReactionTypeEmoji, MessageEntity
import sqlite3
import threading
import json
import time
import os
import requests
import yt_dlp

# توکن ربات
TOKEN = "9032432816:AAEPZiX2VV2D5ppXpxsUUCAE7yJjn1swrTY"

ADMIN_IDS = [7904239647, 1000843522, 7856135158, 5528031877, 1251098392, 6915992479, 6573124305]

REQUIRED_CHANNELS = [
    {
        "id": "@Footy_Fuck",
        "url": "https://t.me/Footy_Fuck",
        "name": "عضویت در کانال اول 📢"
    },
    {
        "id": -1002568283880,
        "url": "https://t.me/+z_GCwt_dtc5mYzRk",
        "name": "عضویت در کانال دوم 📢"
    }
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
            if status not in ['member', 'administrator', 'creator']:
                return False
        except Exception:
            return False
    return True

# ۱. هندلر استارت و قفل چنل
@bot.message_handler(commands=['start'])
def start_command(message):
    text = message.text.split()
    payload = text[1] if len(text) > 1 else ""

    if not check_membership(message.from_user.id):
        markup = InlineKeyboardMarkup()
        for channel in REQUIRED_CHANNELS:
            markup.row(InlineKeyboardButton(channel["name"], url=channel["url"]))

        bot_info = bot.get_me()
        if payload.startswith("f_"):
            markup.row(InlineKeyboardButton("عضو شدم، دریافت فایل 🔄", url=f"https://t.me/{bot_info.username}?start={payload}"))
        else:
            markup.row(InlineKeyboardButton("عضو شدم 🔄", url=f"https://t.me/{bot_info.username}?start=start"))

        bot.reply_to(message, "⛔️ برای استفاده از ربات و دریافت فایل، ابتدا باید در کانال‌های زیر عضو شوید:", reply_markup=markup)
        return

    if not payload or payload == "start":
        bot.reply_to(message, "به ربات خوش آمدید ✅")
        return

    if payload.startswith("f_"):
        try:
            file_db_id = int(payload.split("_")[1])
            cursor.execute("SELECT file_id, media_type, caption, entities FROM files WHERE id = ?", (file_db_id,))
            result = cursor.fetchone()

            if result:
                file_id, media_type, caption_text, entities_json = result
                sent_msg = None

                parsed_entities = None
                if entities_json:
                    entities_list = json.loads(entities_json)
                    parsed_entities = [telebot.types.MessageEntity(**e) for e in entities_list]

                send_kwargs = {
                    'chat_id': message.chat.id,
                    'caption': caption_text,
                    'caption_entities': parsed_entities
                }

                if media_type == 'doc': sent_msg = bot.send_document(document=file_id, **send_kwargs)
                elif media_type == 'vid': sent_msg = bot.send_video(video=file_id, **send_kwargs)
                elif media_type == 'aud': sent_msg = bot.send_audio(audio=file_id, **send_kwargs)
                elif media_type == 'pho': sent_msg = bot.send_photo(photo=file_id, **send_kwargs)

                if sent_msg:
                    warning_msg = bot.reply_to(sent_msg, "⚠️ این فایل تا 60 ثانیه دیگر پاک می‌شود. لطفاً آن را ذخیره کنید.")
                    timer = threading.Timer(60.0, delete_messages, args=(message.chat.id, sent_msg.message_id, warning_msg.message_id))
                    timer.start()
            else:
                bot.reply_to(message, "❌ فایل مورد نظر یافت نشد.")
        except Exception:
            bot.reply_to(message, "❌ خطایی رخ داد.")

# ۲. دریافت فایل از ادمین برای ساخت لینک (فقط در چت خصوصی)
@bot.message_handler(content_types=['document', 'video', 'audio', 'photo'])
def receive_file(message):
    if message.chat.type in ['group', 'supergroup']:
        return
    if message.from_user.id not in ADMIN_IDS:
        return

    file_id = None
    media_type = None

    if message.document: file_id = message.document.file_id; media_type = 'doc'
    elif message.video: file_id = message.video.file_id; media_type = 'vid'
    elif message.audio: file_id = message.audio.file_id; media_type = 'aud'
    elif message.photo: file_id = message.photo[-1].file_id; media_type = 'pho'

    if file_id and media_type:
        pending_files[message.chat.id] = {'file_id': file_id, 'media_type': media_type}
        msg = bot.reply_to(message, "✅ فایل دریافت شد.\n\n✍️ حالا لطفاً **کپشن** را بفرستید.\n🔸 اگر کپشن نمی‌خواهید دستور /skip را بفرستید.", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_caption)

# ۳. دریافت کپشن و صدور لینک
def process_caption(message):
    if message.chat.id not in pending_files: return

    file_info = pending_files[message.chat.id]
    caption_text = None
    entities_json = None

    if message.text and message.text != '/skip':
        caption_text = message.text
        if message.entities:
            entities_list = []
            for ent in message.entities:
                ent_dict = {
                    'type': ent.type, 'offset': ent.offset, 'length': ent.length,
                    'url': ent.url, 'custom_emoji_id': ent.custom_emoji_id
                }
                ent_dict = {k: v for k, v in ent_dict.items() if v is not None}
                entities_list.append(ent_dict)
            entities_json = json.dumps(entities_list)

    cursor.execute("INSERT INTO files (file_id, media_type, caption, entities) VALUES (?, ?, ?, ?)",
                   (file_info['file_id'], file_info['media_type'], caption_text, entities_json))
    conn.commit()
    short_id = cursor.lastrowid

    del pending_files[message.chat.id]

    bot_info = bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=f_{short_id}"
    bot.reply_to(message, f"✅ فایل با موفقیت ثبت شد.\n\n🔗 لینک اختصاصی:\n`{link}`", parse_mode='Markdown')

# هندلر هوشمند لینک‌های شبکه‌های اجتماعی
@bot.message_handler(func=lambda message: message.text and any(domain in message.text for domain in ['instagram.com', 'twitter.com', 'x.com', 'youtube.com', 'youtu.be']))
def handle_social_links(message):
    url = message.text.strip()
    chat_id = message.chat.id
    message_id = message.message_id
    is_group = message.chat.type in ['group', 'supergroup']

    if is_group:
        try:
            bot.set_message_reaction(chat_id, message_id, [ReactionTypeEmoji("👀")])
        except Exception:
            pass

    reply_to = message_id if is_group else None
    processing_msg = bot.send_message(chat_id, "⏳ در حال پردازش و دانلود رسانه...", reply_to_message_id=reply_to)

    try:
        # مدیریت توییتر مستقیماً با تنظیمات اختصاصی yt-dlp بدون نیاز به سرور واسطه
        output_template = f"media_{chat_id}_{message_id}.%(ext)s"

        ydl_opts = {
            'outtmpl': output_template,
            'format': 'best',
            'noplaylist': True,
            'socket_timeout': 30,
            'geo_bypass': True,
            'nocheckcertificate': True,
            'extractor_args': {
                'twitter': {
                    'api_version': ['graphql']
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
        }

        # اگر فایل کوکی توییتر هم داری اعمالش کند
        if ('twitter.com' in url or 'x.com' in url) and os.path.exists('cookiesx.txt'):
            ydl_opts['cookiefile'] = 'cookiesx.txt'
        elif 'instagram.com' in url and os.path.exists('cookies.txt'):
            ydl_opts['cookiefile'] = 'cookies.txt'

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            original_caption = info.get('description', 'کپشنی موجود نیست.')

        social_captions[filename] = original_caption

        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("مشاهده کپشن 📋", callback_data=f"show_cap_{filename}"))

        with open(filename, 'rb') as f:
            if filename.endswith(('.mp4', '.mkv', '.webm', '.mov')):
                bot.send_video(chat_id, f, caption="✨✨", reply_to_message_id=message_id, reply_markup=markup)
            elif filename.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                bot.send_photo(chat_id, f, caption="✨✨", reply_to_message_id=message_id, reply_markup=markup)
            else:
                bot.send_document(chat_id, f, caption="✨✨", reply_to_message_id=message_id, reply_markup=markup)

        if os.path.exists(filename):
            os.remove(filename)

        bot.delete_message(chat_id, processing_msg.message_id)

    except Exception as e:
        print(f"Error details: {e}")
        try:
            bot.edit_message_text("❌ دانلود از این لینک با خطا مواجه شد.", chat_id, processing_msg.message_id)
        except:
            pass

# هندلر نمایش کپشن
@bot.callback_query_handler(func=lambda call: call.data.startswith('show_cap_'))
def callback_show_caption(call):
    filename_key = call.data.replace('show_cap_', '')
    caption = social_captions.get(filename_key, "کپشن این پست یافت نشد یا منقضی شده است.")
    bot.answer_callback_query(call.id, text=caption[:200], show_alert=True)

if __name__ == "__main__":
    print("Bot is running...")
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception:
            time.sleep(3)
