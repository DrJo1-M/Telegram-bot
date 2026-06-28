import os
import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

TOKEN = "8754033877:AAH2Pn1oVPYDXSXXu4sNURo6hPb8E09sz1U"

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    await update.message.reply_text("⏳ جاري التحميل...")
    
    try:
        ydl_opts = {
            'outtmpl': '/tmp/video.%(ext)s',
            'format': 'best',
            'cookiefile': '/app/cookies.txt',
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
        
        with open(filename, 'rb') as video:
            await update.message.reply_video(video)
        
        os.remove(filename)
        
    except Exception as e:
        await update.message.reply_text(f"❌ حصل خطأ: {str(e)}")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
app.run_polling()
