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


if __name__ == '__main__':
  asyncio.run(main())
