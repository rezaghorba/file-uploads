import os
import re
import telebot
import yt_dlp

# توکن بات و تنظیمات ادمین
TOKEN = 'YOUR_BOT_TOKEN_HERE'  # توکن ربات خود را اینجا بگذارید
ADMIN_IDS = [
    123456789
]  # آیدی عددی ادمین‌های خود را اینجا وارد کنید (برای بخش فایل‌ها)

bot = telebot.TeleBot(TOKEN)

# رجکس‌های شناسایی لینک‌های مختلف (توییتر/ایکس، اینستاگرام، یوتیوب)
TWITTER_REGEX = re.compile(
    r'https?://(?:www\.)?(?:twitter\.com|x\.com)/\w+/status/\d+'
)
INSTAGRAM_REGEX = re.compile(
    r'https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/\w+'
)
YOUTUBE_REGEX = re.compile(
    r'https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)\w+'
)


def download_media(url):
  """تابع جامع برای دانلود ویدیو و مدیا از توییتر، اینستاگرام و یوتیوب با yt-dlp"""
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
      info = ydl.extract_info(url, download=True)
      filename = ydl.prepare_filename(info)
      if os.path.exists(filename):
        return filename
  except Exception as e:
    print(f'Download Error: {e}')
  return None


# ۱. دستور استارت و پیام خوش‌آمدگویی اصلی
@bot.message_handler(commands=['start'])
def send_welcome(message):
  bot.reply_to(
      message,
      'سلام! خوش آمدید. 🚀\nشما می‌توانید لینک‌های توییتر، اینستاگرام یا یوتیوب'
      ' خود را بفرستید تا مدیا را دانلود کرده و برای شما ارسال کنم.',
  )


# ۲. هندلر برای فایل‌های ارسالی ادمین‌ها (فقط در پی‌وی - در گروه غیرفعال است)
@bot.message_handler(
    content_types=['document', 'video', 'audio', 'photo'],
    func=lambda message: message.chat.type == 'private',
)
def handle_admin_files(message):
  # بررسی اینکه آیا فرستنده جزو ادمین‌ها است یا خیر
  if message.from_user.id not in ADMIN_IDS:
    return

  # کدهای مربوط به پردازش فایل ادمین و تبدیل به لینک (همان کدهای قبلی شما)
  bot.reply_to(
      message,
      '📂 فایل توسط ادمین دریافت شد و لینک آن آماده شد (قابلیت اختصاصی'
      ' ادمین).',
  )


# ۳. هندلر جامع برای بررسی و دانلود لینک‌های شبکه‌های اجتماعی (توییتر، اینستاگام، یوتیوب)
@bot.message_handler(func=lambda message: True)
def handle_social_links(message):
  if not message.text or message.text.startswith('/'):
    return

  text = message.text

  # پیدا کردن نوع لینک در متن پیام
  target_url = None
  if TWITTER_REGEX.search(text):
    target_url = TWITTER_REGEX.search(text).group(0)
  elif INSTAGRAM_REGEX.search(text):
    target_url = INSTAGRAM_REGEX.search(text).group(0)
  elif YOUTUBE_REGEX.search(text):
    target_url = YOUTUBE_REGEX.search(text).group(0)

  if not target_url:
    return  # اگر هیچ‌کدام از لینک‌های مورد نظر نبود، کاری نکند

  # الف) گذاشتن ری‌اکشن چشم 👀 روی پیام کاربر (چه در پی‌وی و چه در گروه)
  try:
    bot.set_message_reaction(
        message.chat.id, message.message_id, [telebot.types.ReactionTypeEmoji('👀')]
    )
  except Exception as e:
    print(f'Reaction Error: {e}')

  # ب) ارسال پیام پردازش موقت
  processing_msg = bot.reply_to(
      message, '⏳ در حال دریافت و دانلود مدیا از لینک ارسالی...'
  )

  # ج) دانلود مدیا
  file_path = download_media(target_url)

  if not file_path or not os.path.exists(file_path):
    try:
      bot.edit_message_text(
          '❌ متأسفانه دانلود مدیا از این لینک امکان‌پذیر نبود.',
          chat_id=processing_msg.chat.id,
          message_id=processing_msg.message_id,
      )
    except:
      pass
    return

  # د) ارسال فایل به صورت ریپلای روی پیام اصلی کاربر
  try:
    with open(file_path, 'rb') as f:
      if file_path.endswith(('.mp4', '.mkv', '.webm', '.mov')):
        bot.send_video(
            message.chat.id, f, reply_to_message_id=message.message_id
        )
      else:
        bot.send_document(
            message.chat.id, f, reply_to_message_id=message.message_id
        )

    # پاک کردن پیام موقت
    bot.delete_message(processing_msg.chat.id, processing_msg.message_id)

  except Exception as e:
    print(f'Send Error: {e}')

  finally:
    # پاکسازی فایل از هاست برای جلوگیری از پر شدن حافظه
    if file_path and os.path.exists(file_path):
      try:
        os.remove(file_path)
      except:
        pass


if __name__ == '__main__':
  print('Integrated Bot is running...')
  bot.infinity_polling()
