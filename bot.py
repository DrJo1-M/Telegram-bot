import os
import re
import logging
import tempfile
import requests
from pathlib import Path
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ─── إعدادات ──────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "8754033877:AAH2Pn1oVPYDXSXXu4sNURo6hPb8E09sz1U")

# الحد الأقصى لحجم الملف اللي تليجرام بيقبله (50MB للبوتات العادية)
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Headers لتجنب الحجب
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Referer": "",  # بعض المواقع بتحتاج Referer
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── دوال مساعدة ──────────────────────────────────────────────────────────────

def is_direct_video_link(url: str) -> bool:
    """يتحقق لو الرابط مباشر لملف فيديو"""
    video_extensions = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".flv", ".ts")
    path = url.split("?")[0].lower()
    return any(path.endswith(ext) for ext in video_extensions)

def get_filename_from_url(url: str) -> str:
    """يستخرج اسم الملف من الرابط"""
    path = url.split("?")[0]
    name = path.split("/")[-1]
    # تنظيف الاسم
    name = re.sub(r"[^\w\.\-]", "_", name)
    return name if name else "video.mp4"

def get_file_size(url: str) -> int | None:
    """يجيب حجم الملف قبل التنزيل"""
    try:
        resp = requests.head(url, headers=HEADERS, timeout=10, allow_redirects=True)
        size = resp.headers.get("Content-Length")
        return int(size) if size else None
    except Exception:
        return None

def download_video(url: str, dest_path: str, progress_callback=None) -> bool:
    """ينزل الفيديو ويحفظه"""
    try:
        with requests.get(url, headers=HEADERS, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", 0))
            downloaded = 0
            last_reported = 0

            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 512):  # 512KB chunks
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        # أبلغ كل 10%
                        if total and progress_callback:
                            pct = int(downloaded / total * 100)
                            if pct >= last_reported + 10:
                                last_reported = pct
                                progress_callback(pct, downloaded, total)
        return True
    except Exception as e:
        logger.error(f"Download error: {e}")
        return False

def format_size(size_bytes: int) -> str:
    """يحول الحجم لصيغة مقروءة"""
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"

# ─── هاندلرز البوت ────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً! أنا بوت تنزيل الفيديوهات\n\n"
        "📤 ابعتلي رابط مباشر لفيديو (.mp4, .mkv, ...)\n"
        "وهنزله وأبعته ليك على طول!\n\n"
        f"⚠️ الحد الأقصى: {MAX_FILE_SIZE_MB}MB"
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 **طريقة الاستخدام:**\n\n"
        "1. كوبي الرابط المباشر للفيديو\n"
        "2. ابعته هنا في المحادثة\n"
        "3. استنى شوية والبوت هينزله ويبعهولك\n\n"
        "✅ الروابط المدعومة: أي رابط مباشر ينتهي بـ .mp4 أو .mkv وغيرهم\n"
        f"📦 الحد الأقصى للحجم: {MAX_FILE_SIZE_MB}MB",
        parse_mode="Markdown"
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """المعالج الرئيسي لما حد يبعت رابط"""
    text = update.message.text.strip()

    # استخرج الروابط من الرسالة
    urls = re.findall(r'https?://\S+', text)
    if not urls:
        await update.message.reply_text("❌ مش لاقي رابط في رسالتك، ابعت رابط مباشر للفيديو.")
        return

    url = urls[0]  # خد الرابط الأول

    if not is_direct_video_link(url):
        await update.message.reply_text(
            "⚠️ الرابط ده مش رابط فيديو مباشر.\n"
            "محتاج رابط ينتهي بـ .mp4 أو .mkv أو غيرهم."
        )
        return

    # تحقق من الحجم
    status_msg = await update.message.reply_text("🔍 بفحص الرابط...")
    file_size = get_file_size(url)

    if file_size and file_size > MAX_FILE_SIZE_BYTES:
        await status_msg.edit_text(
            f"❌ الملف كبير جداً!\n"
            f"📦 الحجم: {format_size(file_size)}\n"
            f"🚫 الحد الأقصى: {MAX_FILE_SIZE_MB}MB"
        )
        return

    size_text = f" ({format_size(file_size)})" if file_size else ""
    await status_msg.edit_text(f"⬇️ بنزل الفيديو{size_text}...")

    filename = get_filename_from_url(url)

    with tempfile.TemporaryDirectory() as tmpdir:
        dest = os.path.join(tmpdir, filename)

        # دالة تحديث التقدم
        last_pct = {"v": 0}
        async def update_progress(pct, dl, total):
            if pct != last_pct["v"]:
                last_pct["v"] = pct
                try:
                    await status_msg.edit_text(
                        f"⬇️ جاري التنزيل... {pct}%\n"
                        f"📥 {format_size(dl)} / {format_size(total)}"
                    )
                except Exception:
                    pass

        # نزل الفيديو (sync, نشغله في thread)
        import asyncio
        loop = asyncio.get_event_loop()

        progress_calls = []
        def sync_progress(pct, dl, total):
            progress_calls.append((pct, dl, total))

        success = await loop.run_in_executor(
            None,
            lambda: download_video(url, dest, sync_progress)
        )

        # حدث progress آخر مرة
        for pct, dl, total in progress_calls[-1:]:
            try:
                await status_msg.edit_text(f"⬇️ اكتمل التنزيل {pct}%، بيتم الرفع...")
            except Exception:
                pass

        if not success or not os.path.exists(dest):
            await status_msg.edit_text("❌ فشل التنزيل! تأكد من الرابط وحاول تاني.")
            return

        actual_size = os.path.getsize(dest)
        if actual_size > MAX_FILE_SIZE_BYTES:
            await status_msg.edit_text(
                f"❌ الملف اتنزل ({format_size(actual_size)}) لكن أكبر من الحد المسموح ({MAX_FILE_SIZE_MB}MB)."
            )
            return

        # ابعت الملف
        await status_msg.edit_text("📤 بيتم الرفع على تليجرام...")
        try:
            with open(dest, "rb") as f:
                await update.message.reply_video(
                    video=f,
                    filename=filename,
                    caption=f"✅ {filename}\n📦 {format_size(actual_size)}",
                    supports_streaming=True,
                )
            await status_msg.delete()
        except Exception as e:
            logger.error(f"Upload error: {e}")
            # لو upload_video فشل حاول ك document
            try:
                with open(dest, "rb") as f:
                    await update.message.reply_document(
                        document=f,
                        filename=filename,
                        caption=f"✅ {filename}\n📦 {format_size(actual_size)}",
                    )
                await status_msg.delete()
            except Exception as e2:
                await status_msg.edit_text(f"❌ فشل الإرسال: {e2}")

# ─── تشغيل البوت ──────────────────────────────────────────────────────────────

def main():
    if BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        print("❌ ضع الـ BOT_TOKEN في المتغير أو شغل: BOT_TOKEN=xxx python telegram_video_bot.py")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    print("✅ البوت شغال! ابعت رابط على تليجرام.")
    app.run_polling()

if __name__ == "__main__":
    main()
