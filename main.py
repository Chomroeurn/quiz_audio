"""
Khmer TTS Telegram Bot - Simple & Stable Female Voice
=====================================================

A reliable Khmer Text-to-Speech bot with minimal dependencies and maximum stability.

Features:
- Uses gTTS for natural Khmer female voice
- Simple audio enhancement (optional)
- Rock-solid stability with extensive error handling
- Auto text splitting for long messages
- Health check endpoint

Requirements:
    pip install python-telegram-bot==13.17 gTTS

Optional enhancement:
    pip install pydub

"""

import os
import logging
import tempfile
import threading
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from gtts import gTTS
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# Simple audio enhancement (optional)
try:
    from pydub import AudioSegment
    HAS_AUDIO_PROCESSING = True
    print("✅ Audio processing available")
except ImportError:
    HAS_AUDIO_PROCESSING = False
    print("ℹ️ Audio processing disabled (install pydub for enhancement)")

# Configuration
LANG = 'km'
CHUNK_SIZE = 2500
PORT = int(os.getenv('PORT', 8080))
audio_counter = 0

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get token
TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    print("❌ Error: TELEGRAM_TOKEN environment variable not set!")
    print("Set it with: export TELEGRAM_TOKEN='your_bot_token'")
    sys.exit(1)


class SimpleHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Khmer Female TTS Bot - OK')
    
    def log_message(self, format, *args):
        pass  # Suppress HTTP logs


def start_health_server():
    try:
        server = HTTPServer(('0.0.0.0', PORT), SimpleHealthHandler)
        server.serve_forever()
    except Exception as e:
        logger.error(f'Health server error: {e}')


def safe_split_text(text, max_len=CHUNK_SIZE):
    """Ultra-safe text splitting"""
    if not text or len(text) <= max_len:
        return [text] if text else []
    
    # Simple splitting on common boundaries
    chunks = []
    words = text.split()
    current = ""
    
    for word in words:
        test_chunk = f"{current} {word}".strip()
        if len(test_chunk) <= max_len:
            current = test_chunk
        else:
            if current:
                chunks.append(current)
            current = word
    
    if current:
        chunks.append(current)
    
    return chunks if chunks else [text[:max_len]]


def enhance_audio_simple(input_file, output_file):
    """Very simple audio enhancement if pydub available"""
    if not HAS_AUDIO_PROCESSING:
        # No processing - just copy
        with open(input_file, 'rb') as src, open(output_file, 'wb') as dst:
            dst.write(src.read())
        return True
    
    try:
        audio = AudioSegment.from_mp3(input_file)
        # Very gentle enhancement
        enhanced = audio + 1  # Slight volume boost
        enhanced.export(output_file, format="mp3")
        return True
    except Exception as e:
        logger.warning(f'Audio enhancement failed: {e}')
        # Fallback to copy
        with open(input_file, 'rb') as src, open(output_file, 'wb') as dst:
            dst.write(src.read())
        return False


def create_tts_audio(text):
    """Create TTS audio file - ultra-safe version"""
    temp_files = []
    
    try:
        # Create temp files
        _, raw_file = tempfile.mkstemp(suffix='.mp3', prefix='tts_raw_')
        _, final_file = tempfile.mkstemp(suffix='.mp3', prefix='tts_final_')
        temp_files = [raw_file, final_file]
        
        # Generate TTS
        logger.info(f'Generating TTS for text length: {len(text)}')
        tts = gTTS(text=text, lang=LANG, slow=False)
        tts.save(raw_file)
        
        # Enhance if possible
        enhance_audio_simple(raw_file, final_file)
        
        # Clean up raw file
        try:
            os.remove(raw_file)
        except:
            pass
        
        return final_file
        
    except Exception as e:
        logger.error(f'TTS creation failed: {e}')
        # Clean up all temp files
        for f in temp_files:
            try:
                os.remove(f)
            except:
                pass
        raise Exception(f'Failed to create audio: {str(e)}')


def send_tts(update, context, text):
    """Main TTS sending function"""
    global audio_counter
    
    if not text or not text.strip():
        update.message.reply_text("Please provide some text to convert to speech.")
        return
    
    chat_id = update.effective_chat.id
    text = text.strip()
    
    logger.info(f'TTS request: chat_id={chat_id}, text_length={len(text)}')
    
    # Show processing message
    try:
        status_msg = context.bot.send_message(
            chat_id=chat_id,
            text="🎵 Creating audio... Please wait."
        )
    except:
        status_msg = None
    
    # Split text safely
    chunks = safe_split_text(text)
    files_created = []
    
    try:
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            
            audio_counter += 1
            audio_id = f"Updated{audio_counter:03d}"
            
            try:
                # Create audio
                audio_file = create_tts_audio(chunk)
                files_created.append(audio_file)
                
                # Send audio
                with open(audio_file, 'rb') as f:
                    caption = f"🎧 {audio_id} - Khmer Female Update88"
                    if len(chunks) > 1:
                        caption += f" (Part {i+1}/{len(chunks)})"
                    
                    if HAS_AUDIO_PROCESSING:
                        caption += " [Enhanced]"
                    
                    context.bot.send_audio(
                        chat_id=chat_id,
                        audio=f,
                        filename=f'{audio_id}.mp3',
                        caption=caption,
                        title=f'Khmer TTS {audio_id}'
                    )
                
                logger.info(f'✅ Sent audio {audio_id}')
                
            except Exception as e:
                logger.error(f'Failed to process chunk {i+1}: {e}')
                context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Failed to create audio for part {i+1}. Continuing..."
                )
        
        logger.info(f'✅ Completed TTS request - {len(chunks)} chunks processed')
        
    except Exception as e:
        logger.error(f'TTS process failed: {e}')
        try:
            context.bot.send_message(
                chat_id=chat_id,
                text="❌ Sorry, something went wrong. Please try again.\n"
                     "សុំទោស! មានបញ្ហា។ សូមព្យាយាមម្ដងទៀត។"
            )
        except:
            pass
    
    finally:
        # Clean up all files
        for file_path in files_created:
            try:
                os.remove(file_path)
            except:
                pass
        
        # Remove status message
        if status_msg:
            try:
                context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
            except:
                pass


# Bot command handlers
def cmd_start(update, context):
    enhancement_status = "Enhanced" if HAS_AUDIO_PROCESSING else "Standard"
    
    message = (
        f"សួស្តី! 🇰🇭👩\n\n"
        f"🎙️ Khmer Female Voice TTS Bot ({enhancement_status})\n\n"
        f"Features:\n"
        f"• Natural Khmer female voice\n"
        f"• Automatic text splitting\n"
        f"• Supports long messages\n"
    )
    
    if HAS_AUDIO_PROCESSING:
        message += "• Audio enhancement enabled\n"
    else:
        message += "• Install pydub for audio enhancement\n"
    
    message += (
        f"\nUsage:\n"
        f"• Send any Khmer text directly\n"
        f"• /speak <text> - Convert specific text\n"
        f"• /help - Show help\n\n"
        f"Example: សួស្ដីអ្នកសុខសប្បាយទេ"
    )
    
    update.message.reply_text(message)


def cmd_help(update, context):
    help_text = (
        "🎧 Khmer Female TTS Bot Help\n\n"
        "📝 How to use:\n"
        "• Send any text message → Get audio\n"
        "• /speak <your text> → Convert text\n"
        "• Works with Khmer and English\n"
        "• Long texts are split automatically\n\n"
        "Examples:\n"
        "• សួស្ដីអ្នកសុខសប្បាយទេ\n"
        "• /speak ថ្ងៃនេះអាកាសធាតុល្អ\n"
        "• Hello mixed ជាមួយ Khmer\n\n"
        f"Status: {'Enhanced audio' if HAS_AUDIO_PROCESSING else 'Basic audio'}"
    )
    
    if not HAS_AUDIO_PROCESSING:
        help_text += "\n\n💡 For better audio quality:\npip install pydub"
    
    update.message.reply_text(help_text)


def cmd_speak(update, context):
    text = ' '.join(context.args)
    if not text:
        update.message.reply_text(
            "Please provide text after /speak\n\n"
            "Example: /speak សួស្ដីអ្នកសុខសប្បាយទេ"
        )
        return
    
    send_tts(update, context, text)


def handle_text(update, context):
    text = update.message.text
    if text and text.strip():
        send_tts(update, context, text)


def handle_error(update, context):
    logger.error(f'Bot error: {context.error}')
    if update and update.effective_chat:
        try:
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ An error occurred. Please try again."
            )
        except:
            pass


def main():
    print("=" * 50)
    print("🎙️ KHMER FEMALE TTS BOT")
    print("=" * 50)
    print(f"Audio Processing: {'✅ Enabled' if HAS_AUDIO_PROCESSING else '❌ Disabled'}")
    print(f"Language: {LANG}")
    print(f"Chunk Size: {CHUNK_SIZE}")
    print(f"Health Check Port: {PORT}")
    print("=" * 50)
    
    # Start health check server
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    print(f"📡 Health check: http://localhost:{PORT}")
    
    # Create bot
    try:
        updater = Updater(TOKEN, use_context=True)
        dp = updater.dispatcher
        
        # Add handlers
        dp.add_handler(CommandHandler('start', cmd_start))
        dp.add_handler(CommandHandler('help', cmd_help))
        dp.add_handler(CommandHandler('speak', cmd_speak))
        dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
        dp.add_error_handler(handle_error)
        
        print("🚀 Starting bot...")
        updater.start_polling(drop_pending_updates=True)
        print("✅ Bot running! Send /start to test.")
        updater.idle()
        
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
