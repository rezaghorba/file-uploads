
import os
import re
import glob
import json
import time
import uuid
import shutil
import sqlite3
import tempfile
import threading
import logging
from io import BytesIO

import requests
import telebot
import yt_dlp

from PIL import Image, ImageOps, UnidentifiedImageError

from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    ReactionTypeEmoji,
)


# ================= CONFIG =================

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise RuntimeError("TOKEN environment variable is missing")

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

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "en-US,en;q=0.5",
}

SOCIAL_DOMAINS = [
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "youtu.be",
]

MAX_IMAGE_SIZE = 25 * 1024 * 1024
MAX_VIDEO_SIZE = 100 * 1024 * 1024

VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov")
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".jfif")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

bot = telebot.TeleBot(TOKEN)

pending_files = {}
social_captions = {}


# ================= DATABASE =================

conn = sqlite3.connect(
    "bot_data.db",
    check_same_thread=False,
)

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

db_lock = threading.Lock()


# ================= UTILITIES =================

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
            status = bot.get_chat_member(
                channel["id"],
                user_id,
            ).status

            if status not in [
                "member",
                "administrator",
                "creator",
            ]:
                return False

        except Exception as e:
            logger.warning("Membership error: %s", e)
            return False

    return True


# ================= START / FILE LINKS =================

@bot.message_handler(commands=["start"])
def start_command(message):
    parts = message.text.split()
    payload = parts[1] if len(parts) > 1 else ""

    if not check_membership(message.from_user.id):

        markup = InlineKeyboardMarkup()

        for channel in REQUIRED_CHANNELS:
            markup.row(
                InlineKeyboardButton(
                    channel["name"],
                    url=channel["url"],
                )
            )

        bot_info = bot.get_me()

        if payload.startswith("f_"):
            callback_payload = payload
        else:
            callback_payload = "start"

        markup.row(
            InlineKeyboardButton(
                "عضو شدم 🔄",
                url=(
                    f"https://t.me/{bot_info.username}"
                    f"?start={callback_payload}"
                ),
            )
        )

        bot.reply_to(
            message,
            "⛔️ برای استفاده از ربات ابتدا در کانال‌های زیر عضو شوید:",
            reply_markup=markup,
        )
        return

    if not payload or payload == "start":
        bot.reply_to(message, "به ربات خوش آمدید ✅")
        return

    if payload.startswith("f_"):
        try:
            file_db_id = int(payload.split("_", 1)[1])

            with db_lock:
                cursor.execute(
                    """
                    SELECT file_id, media_type, caption, entities
                    FROM files WHERE id = ?
                    """,
                    (file_db_id,),
                )
                result = cursor.fetchone()

            if not result:
                bot.reply_to(
                    message,
                    "❌ فایل مورد نظر یافت نشد.",
                )
                return

            file_id, media_type, caption, entities_json = result

            parsed_entities = None

            if entities_json:
                entities = json.loads(entities_json)

                parsed_entities = [
                    telebot.types.MessageEntity(**e)
                    for e in entities
                ]

            kwargs = {
                "chat_id": message.chat.id,
                "caption": caption,
                "caption_entities": parsed_entities,
            }

            if media_type == "doc":
                sent = bot.send_document(
                    document=file_id,
                    **kwargs,
                )

            elif media_type == "vid":
                sent = bot.send_video(
                    video=file_id,
                    **kwargs,
                )

            elif media_type == "aud":
                sent = bot.send_audio(
                    audio=file_id,
                    **kwargs,
                )

            elif media_type == "pho":
                sent = bot.send_photo(
                    photo=file_id,
                    **kwargs,
                )

            else:
                return

            warning = bot.reply_to(
                sent,
                "⚠️ این فایل تا 60 ثانیه دیگر پاک می‌شود. آن را ذخیره کنید.",
            )

            timer = threading.Timer(
                60,
                delete_messages,
                args=(
                    message.chat.id,
                    sent.message_id,
                    warning.message_id,
                ),
            )

            timer.daemon = True
            timer.start()

        except Exception:
            logger.exception("File delivery failed")
            bot.reply_to(message, "❌ خطایی رخ داد.")


# ================= ADMIN FILE UPLOAD =================

@bot.message_handler(
    content_types=["document", "video", "audio", "photo"]
)
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

    if not file_id:
        return

    pending_files[message.chat.id] = {
        "file_id": file_id,
        "media_type": media_type,
    }

    msg = bot.reply_to(
        message,
        "✅ فایل دریافت شد.\n\n"
        "✍️ کپشن را ارسال کنید.\n"
        "برای بدون کپشن بودن /skip را بفرستید.",
    )

    bot.register_next_step_handler(
        msg,
        process_caption,
    )


def process_caption(message):

    chat_id = message.chat.id

    if chat_id not in pending_files:
        return

    if message.from_user.id not in ADMIN_IDS:
        return

    if not message.text:
        bot.reply_to(
            message,
            "لطفاً کپشن متنی بفرستید یا /skip را ارسال کنید.",
        )
        bot.register_next_step_handler(
            message,
            process_caption,
        )
        return

    file_info = pending_files[chat_id]

    caption = None
    entities_json = None

    if message.text != "/skip":

        caption = message.text

        if message.entities:
            entities = []

            for ent in message.entities:
                item = {
                    "type": ent.type,
                    "offset": ent.offset,
                    "length": ent.length,
                }

                if ent.url:
                    item["url"] = ent.url

                if ent.custom_emoji_id:
                    item["custom_emoji_id"] = ent.custom_emoji_id

                entities.append(item)

            entities_json = json.dumps(entities)

    with db_lock:
        cursor.execute(
            """
            INSERT INTO files
            (file_id, media_type, caption, entities)
            VALUES (?, ?, ?, ?)
            """,
            (
                file_info["file_id"],
                file_info["media_type"],
                caption,
                entities_json,
            ),
        )

        conn.commit()
        short_id = cursor.lastrowid

    del pending_files[chat_id]

    bot_info = bot.get_me()

    link = (
        f"https://t.me/{bot_info.username}"
        f"?start=f_{short_id}"
    )

    bot.reply_to(
        message,
        f"✅ فایل ثبت شد.\n\n🔗 لینک اختصاصی:\n{link}",
    )


# ================= IMAGE DOWNLOADER =================

def download_image(url, path, headers=None):

    request_headers = dict(headers or HEADERS)

    with requests.get(
        url,
        headers=request_headers,
        stream=True,
        timeout=(15, 60),
        allow_redirects=True,
    ) as response:

        response.raise_for_status()

        data = bytearray()

        for chunk in response.iter_content(65536):

            if chunk:
                data.extend(chunk)

            if len(data) > MAX_IMAGE_SIZE:
                raise ValueError("Image exceeds size limit")

        if not data:
            raise ValueError("Empty image")

    try:

        with Image.open(BytesIO(data)) as img:

            img.load()

            img = ImageOps.exif_transpose(img)

            img = img.convert("RGB")

            img.save(
                path,
                "JPEG",
                quality=95,
                optimize=True,
            )

    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise ValueError(
            "Downloaded content is not a valid image"
        ) from e


# ================= VIDEO DOWNLOADER =================

def download_file(url, path, headers=None):

    total = 0

    with requests.get(
        url,
        headers=headers or HEADERS,
        stream=True,
        timeout=(15, 60),
        allow_redirects=True,
    ) as response:

        response.raise_for_status()

        with open(path, "wb") as f:

            for chunk in response.iter_content(65536):

                if not chunk:
                    continue

                total += len(chunk)

                if total > MAX_VIDEO_SIZE:
                    raise ValueError("Video exceeds size limit")

                f.write(chunk)

    if total == 0:
        raise ValueError("Empty download")


# ================= INSTAGRAM DOWNLOADER =================

class InstagramDownloader:

    def download(self, url):

        raise RuntimeError(
            "Instagram HTML extraction is not reliable. "
            "Use yt-dlp fallback."
        )


def instagram_custom_media(url, workdir):

    raise RuntimeError(
        "Instagram custom extractor unavailable"
    )


# ================= FILE COLLECTION =================

def collect_files(workdir):

    items = []

    for path in sorted(
        glob.glob(
            os.path.join(workdir, "**", "*"),
            recursive=True,
        )
    ):

        if not os.path.isfile(path):
            continue

        if os.path.getsize(path) == 0:
            continue

        low = path.lower()

        if low.endswith(VIDEO_EXT):
            items.append(("video", path))

        elif low.endswith(IMAGE_EXT):
            items.append(("photo", path))

    return items[:10]


# ================= TWITTER / X =================

def twitter_media(url, workdir):

    match = re.search(
        r"(?:twitter|x)\.com/(?:[^/]+/status|i/(?:web/)?status)/(\d+)",
        url,
        re.I,
    )

    if not match:
        raise ValueError("Tweet ID not found")

    tweet_id = match.group(1)

    media = []
    caption = None

    try:

        response = requests.get(
            f"https://api.fxtwitter.com/status/{tweet_id}",
            headers=HEADERS,
            timeout=20,
        )

        response.raise_for_status()

        data = response.json().get("tweet") or {}

        caption = data.get("text")

        for item in (data.get("media") or {}).get("all", []):

            kind = (
                "photo"
                if item.get("type") == "photo"
                else "video"
            )

            if item.get("url"):
                media.append((kind, item["url"]))

    except Exception:
        logger.exception("FxTwitter failed")

    if not media:

        try:

            response = requests.get(
                f"https://api.vxtwitter.com/Twitter/status/{tweet_id}",
                headers=HEADERS,
                timeout=20,
            )

            response.raise_for_status()

            data = response.json()

            caption = caption or data.get("text")

            for item in data.get("media_extended", []):

                kind = (
                    "photo"
                    if item.get("type") == "image"
                    else "video"
                )

                if item.get("url"):
                    media.append((kind, item["url"]))

        except Exception:
            logger.exception("VxTwitter failed")

    if not media:
        raise ValueError("No Twitter media found")

    items = []

    for index, (kind, media_url) in enumerate(media[:10]):

        if kind == "photo":

            path = os.path.join(
                workdir,
                f"twitter_{index}.jpg",
            )

            download_image(media_url, path)

        else:

            path = os.path.join(
                workdir,
                f"twitter_{index}.mp4",
            )

            download_file(media_url, path)

        items.append((kind, path))

    return items, caption


# ================= YT-DLP =================

def ytdlp_media(url, workdir):

    opts = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "outtmpl": os.path.join(
            workdir,
            "%(id)s_%(autonumber)s.%(ext)s",
        ),
        "format": "best[ext=mp4][filesize<50M]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "http_headers": HEADERS,
        "socket_timeout": 30,
        "retries": 2,
    }

    with yt_dlp.YoutubeDL(opts) as ydl:

        info = ydl.extract_info(
            url,
            download=True,
        )

    if info and "entries" in info:

        entries = [
            entry for entry in info["entries"]
            if entry
        ]

        info = entries[0] if entries else info

    caption = (
        info.get("description")
        if info
        else None
    )

    items = collect_files(workdir)

    if not items:
        raise ValueError("No downloaded media")

    return items, caption


# ================= FETCH MEDIA =================

def fetch_media(url, workdir):

    if "instagram.com" in url.lower():

        steps = [ytdlp_media]

    elif re.search(r"(?:twitter|x)\.com/", url, re.I):

        steps = [
            twitter_media,
            ytdlp_media,
        ]

    else:

        steps = [ytdlp_media]

    last_error = None

    for step in steps:

        try:

            for path in glob.glob(
                os.path.join(workdir, "*")
            ):

                if os.path.isfile(path):
                    os.remove(path)

            items, caption = step(url, workdir)

            if items:
                return items, caption

        except Exception as error:

            last_error = error

            logger.exception(
                "Downloader %s failed",
                step.__name__,
            )

    raise RuntimeError(
        str(last_error or "All download methods failed")
    )


# ================= SEND MEDIA =================

def send_items(chat_id, items, reply_to, markup):

    def send_single(kind, path, keyboard):

        with open(path, "rb") as file:

            try:

                if kind == "video":

                    return bot.send_video(
                        chat_id,
                        file,
                        caption="✨✨",
                        reply_to_message_id=reply_to,
                        reply_markup=keyboard,
                        timeout=120,
                    )

                return bot.send_photo(
                    chat_id,
                    file,
                    caption="✨✨",
                    reply_to_message_id=reply_to,
                    reply_markup=keyboard,
                    timeout=120,
                )

            except Exception:

                logger.exception("Media sending failed")

                file.seek(0)

                return bot.send_document(
                    chat_id,
                    file,
                    caption="✨✨",
                    reply_to_message_id=reply_to,
                    reply_markup=keyboard,
                    timeout=120,
                )

    if len(items) == 1:

        send_single(
            items[0][0],
            items[0][1],
            markup,
        )

        return

    handles = []

    try:

        media = []

        for index, (kind, path) in enumerate(items):

            file = open(path, "rb")

            handles.append(file)

            media_type = (
                InputMediaVideo
                if kind == "video"
                else InputMediaPhoto
            )

            media.append(
                media_type(
                    file,
                    caption="✨✨" if index == 0 else None,
                )
            )

        sent = bot.send_media_group(
            chat_id,
            media,
            reply_to_message_id=reply_to,
            timeout=120,
        )

        bot.send_message(
            chat_id,
            "📋",
            reply_to_message_id=sent[0].message_id,
            reply_markup=markup,
        )

    except Exception:

        logger.exception("Media group failed")

        for file in handles:

            try:
                file.close()
            except Exception:
                pass

        for kind, path in items:

            send_single(
                kind,
                path,
                None,
            )

        bot.send_message(
            chat_id,
            "📋",
            reply_markup=markup,
        )

    finally:

        for file in handles:

            try:
                file.close()
            except Exception:
                pass


# ================= SOCIAL LINKS =================

@bot.message_handler(
    func=lambda message: (
        bool(message.text)
        and any(
            domain in message.text.lower()
            for domain in SOCIAL_DOMAINS
        )
    )
)
def handle_social_links(message):

    match = re.search(
        r"https?://[^\s]+",
        message.text,
    )

    if not match:
        return

    url = match.group(0).rstrip(".,!?)\]}>")

    if "instagram.com" in url.lower():
        url = url.split("?")[0]

    chat_id = message.chat.id

    is_group = message.chat.type in [
        "group",
        "supergroup",
    ]

    reply_to = (
        message.message_id
        if is_group
        else None
    )

    if is_group:

        try:

            bot.set_message_reaction(
                chat_id,
                message.message_id,
                [ReactionTypeEmoji("👀")],
            )

        except Exception:
            pass

    processing = bot.send_message(
        chat_id,
        "⏳ در حال دانلود رسانه...",
        reply_to_message_id=reply_to,
    )

    workdir = tempfile.mkdtemp(prefix="dl_")

    try:

        items, caption = fetch_media(
            url,
            workdir,
        )

        key = uuid.uuid4().hex[:12]

        social_captions[key] = (
            caption or "کپشنی موجود نیست."
        )

        markup = InlineKeyboardMarkup()

        markup.row(
            InlineKeyboardButton(
                "مشاهده کپشن 📋",
                callback_data=f"cap_{key}",
            )
        )

        send_items(
            chat_id,
            items,
            reply_to,
            markup,
        )

        delete_messages(
            chat_id,
            processing.message_id,
        )

    except Exception:

        logger.exception("Social download failed")

        try:

            bot.edit_message_text(
                "❌ دانلود این رسانه انجام نشد. لینک یا دسترسی رسانه را بررسی کنید.",
                chat_id,
                processing.message_id,
            )

        except Exception:
            pass

    finally:

        shutil.rmtree(
            workdir,
            ignore_errors=True,
        )


# ================= CAPTION CALLBACK =================

@bot.callback_query_handler(
    func=lambda call: call.data.startswith("cap_")
)
def callback_show_caption(call):

    key = call.data[4:]

    caption = social_captions.get(
        key,
        "کپشن این پست یافت نشد.",
    )

    bot.answer_callback_query(
        call.id,
        text=caption[:200],
        show_alert=True,
    )


# ================= RUN =================

if __name__ == "__main__":

    logger.info("Bot is running...")

    while True:

        try:

            bot.infinity_polling(
                timeout=20,
                long_polling_timeout=10,
                skip_pending=False,
            )

        except Exception:

            logger.exception("Polling error")

            time.sleep(5)
