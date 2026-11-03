import os
import re
import telebot
import yt_dlp

# توکن بات شما
TOKEN = '9032432816:AAEPZiX2VV2D5ppXpxsUUCAE7yJjn1swrTY'
bot = telebot.TeleBot(TOKEN)

# رجکس برای تشخیص لینک توییتر (ایکس)
TWITTER_REGEX = re.compile(
    r'https?://(?:www\.)?(?:twitter\.com|x\.com)/\w+/status/\d+'
)


def download_twitter_media(tweet_url):
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
      if os.path.exists(filename):
        return filename
  except Exception as e:
    print(f'Download Error: {e}')
  return None


@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
  if not message.text:
    return

  # اگر پیام با اسلش شروع شود (مثل دستورات)، نادیده بگیرد
  if message.text.startswith('/'):
    return

  match = TWITTER_REGEX.search(message.text)
  if not match:
    return  # اگر لینک توییتر نبود کاری نکند

  tweet_url = match.group(0)

  # ارسال پیام موقت برای اطلاع‌رسانی
  processing_msg = bot.reply_to(message, '⏳ در حال دریافت و دانلود مدیا از توییتر...')

  # دانلود مدیا
  file_path = download_twitter_media(tweet_url)

  if not file_path or not os.path.exists(file_path):
    try:
      bot.edit_message_text(
          '❌ متأسفانه دانلود از این توییت امکان‌پذیر نبود.',
          chat_id=processing_msg.chat.id,
          message_id=processing_msg.message_id,
      )
    except:
      pass
    return

  # ارسال فایل به صورت ریپلای روی پیام کاربر
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

    # حذف پیام موقت
    bot.delete_message(processing_msg.chat.id, processing_msg.message_id)

  except Exception as e:
    print(f'Send Error: {e}')

  finally:
    # پاکسازی فایل از هاست
    if file_path and os.path.exists(file_path):
      try:
        os.remove(file_path)
      except:
        pass


if __name__ == '__main__':
  print('Bot is running...')
  bot.infinity_polling()

