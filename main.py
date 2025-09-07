"""
Khmer TTS Telegram Bot
======================

This single-file Python bot listens for text messages and replies with a Khmer TTS audio file.

Features:
- Uses `gTTS` for Khmer Text-to-Speech (language code: 'km'). Requires internet.
- Uses `python-telegram-bot` for Telegram integration (v13 style Updater based example).
- Handles `/start` and `/help` commands.
- `/speak <text>` command explicitly creates audio from provided text.
- Any plain text message (non-command) will also be converted to speech.
- Splits long text into chunks to avoid remote TTS length limits.
- Includes health check endpoint for deployment platforms.

Requirements
------------
Install required packages:

    pip install python-telegram-bot==13.17 gTTS

Environment
-----------
Set your Telegram Bot Token in an environment variable named `TELEGRAM_TOKEN`.

Example (Linux/macOS):

    export TELEGRAM_TOKEN="123456:ABC-DEF..."

Run
---

    python khmer_tts_telegram_bot.py

Notes
-----
- gTTS sends requests to Google to get speech; it requires network access.
- If you need higher-quality or offline Khmer TTS, consider Google Cloud Text-to-Speech or another paid TTS provider; that requires additional setup.

"""

import os
import logging
import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from gtts import gTTS
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# Configuration
LANG = 'km'  # Khmer language code
CHUNK_SIZE = 4000  # chunk length for splitting very long texts (characters)
PORT = int(os.getenv('PORT', 8080))  # Port for health check server

# Global counter for audio file IDs
audio_counter = 0

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    logger.error('Please set the TELEGRAM_TOKEN environment variable and restart the bot.')


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Simple health check handler for deployment platforms"""
    def do_GET(self):
        if self.path == '/health' or self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress default HTTP logging
        pass


def start_health_check_server():
    """Start a simple HTTP server for health checks"""
    try:
        server = HTTPServer(('0.0.0.0', PORT), HealthCheckHandler)
        logger.info(f'Health check server started on port {PORT}')
        server.serve_forever()
    except Exception as e:
        logger.error(f'Failed to start health check server: {e}')


def split_text(text: str, chunk_size: int = CHUNK_SIZE):
    """Split text into chunks of roughly chunk_size, trying to split on sentence boundaries.
    Returns a list of text chunks.
    """
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # try to find a sentence boundary (period, question mark, newline) backward from end
        if end < len(text):
            split_at = text.rfind('.', start, end)
            if split_at == -1:
                split_at = text.rfind('\n', start, end)
            if split_at == -1:
                split_at = text.rfind('?', start, end)
            if split_at == -1:
                split_at = text.rfind('!', start, end)
            if split_at == -1 or split_at <= start:
                split_at = end
        else:
            split_at = end

        chunk = text[start:split_at].strip()
        if chunk:
            chunks.append(chunk)
        start = split_at
        if start == end:
            # avoid infinite loop
            start += 1
    return chunks


def text_to_mp3(text: str, lang: str = LANG) -> str:
    """Create an mp3 file from text using gTTS. Returns the file path.

    NOTE: Caller is responsible for deleting the file when finished.
    """
    fd, path = tempfile.mkstemp(suffix='.mp3')
    os.close(fd)

    try:
        tts = gTTS(text=text, lang=lang)
        tts.save(path)
        return path
    except Exception as e:
        # Clean up on error
        try:
            os.remove(path)
        except:
            pass
        raise e


def tts_and_send(update: Update, context: CallbackContext, text: str):
    global audio_counter
    
    chat_id = update.effective_chat.id
    user = update.effective_user
    logger.info('TTS request from user=%s chat_id=%s len=%d', user and user.username, chat_id, len(text))

    # Send processing message
    try:
        processing_msg = context.bot.send_message(chat_id=chat_id, text="🎵 Processing your text... Please wait.")
    except Exception as e:
        logger.error(f'Failed to send processing message: {e}')
        processing_msg = None

    chunks = split_text(text)
    files_to_delete = []
    
    try:
        if len(chunks) == 1:
            audio_counter += 1
            audio_id = f"Gyn{audio_counter:02d}"
            mp3_path = text_to_mp3(chunks[0])
            files_to_delete.append(mp3_path)
            
            with open(mp3_path, 'rb') as f:
                # send as audio (mp3) so user can play it; Telegram will accept mp3 via send_audio
                context.bot.send_audio(
                    chat_id=chat_id, 
                    audio=f, 
                    filename=f'{audio_id}.mp3', 
                    caption=f'🎧 {audio_id} - Khmer TTS'
                )
        else:
            # Multiple chunks: send as a sequence of audios
            for i, chunk in enumerate(chunks, start=1):
                audio_counter += 1
                audio_id = f"Gyn{audio_counter:02d}"
                mp3_path = text_to_mp3(chunk)
                files_to_delete.append(mp3_path)
                
                with open(mp3_path, 'rb') as f:
                    caption = f'🎧 {audio_id} - Part {i}/{len(chunks)}'
                    context.bot.send_audio(
                        chat_id=chat_id, 
                        audio=f, 
                        filename=f'{audio_id}.mp3', 
                        caption=caption
                    )
                    
    except Exception as e:
        logger.exception('Error creating or sending TTS audio: %s', e)
        try:
            update.message.reply_text('Sorry, an error occurred while creating the speech. Please try again.')
        except Exception:
            pass
    finally:
        # Clean up temp files
        for p in files_to_delete:
            try:
                os.remove(p)
            except Exception:
                pass
        
        # Delete processing message
        if processing_msg:
            try:
                context.bot.delete_message(chat_id=chat_id, message_id=processing_msg.message_id)
            except Exception:
                pass


def start_handler(update: Update, context: CallbackContext):
    """Handle /start command"""
    welcome_msg = (
        "សួស្តី! 🇰🇭\n\n"
        "I'm a Khmer Text-to-Speech bot. Send me any Khmer text and I'll convert it to audio!\n\n"
        "Commands:\n"
        "• Just send any text for TTS\n"
        "• /speak <text> - Convert specific text to speech\n"
        "• /help - Show this help message"
    )
    update.message.reply_text(welcome_msg)


def help_handler(update: Update, context: CallbackContext):
    """Handle /help command"""
    help_msg = (
        "🎧 Khmer TTS Bot Help\n\n"
        "How to use:\n"
        "• Send any Khmer text message → Get audio back\n"
        "• /speak <your text> → Convert specific text\n"
        "• Works with both Khmer and English text\n"
        "• Long texts are automatically split into parts\n\n"
        "Example: /speak សួស្ដីអ្នកសុខសប្បាយទេ"
    )
    update.message.reply_text(help_msg)


def speak_handler(update: Update, context: CallbackContext):
    """Handle /speak command"""
    # /speak <text>
    text = ' '.join(context.args)
    if not text:
        update.message.reply_text('Please provide text after /speak\n\nExample: /speak សួស្ដី')
        return
    tts_and_send(update, context, text)


def text_message_handler(update: Update, context: CallbackContext):
    """Handle plain text messages"""
    # For any plain text message, convert to speech
    text = update.message.text
    if not text or text.strip() == '':
        return
    tts_and_send(update, context, text)


def error_handler(update: Update, context: CallbackContext):
    """Handle errors"""
    logger.error('Update caused error: %s', context.error)


def main():
    if not TOKEN:
        raise RuntimeError('TELEGRAM_TOKEN environment variable not set')

    # Start health check server in a separate thread
    health_thread = threading.Thread(target=start_health_check_server, daemon=True)
    health_thread.start()

    # Set up the bot
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Add handlers
    dp.add_handler(CommandHandler('start', start_handler))
    dp.add_handler(CommandHandler('help', help_handler))
    dp.add_handler(CommandHandler('speak', speak_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, text_message_handler))
    dp.add_error_handler(error_handler)

    logger.info('Starting Khmer TTS Telegram bot...')
    logger.info(f'Health check available at http://localhost:{PORT}/health')
    
    # Start the bot
    updater.start_polling(drop_pending_updates=True)
    updater.idle()


if __name__ == '__main__':
    main()
