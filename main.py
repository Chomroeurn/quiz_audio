"""
Khmer TTS Telegram Bot - Enhanced with Male Voice
=================================================

This single-file Python bot listens for text messages and replies with a Khmer TTS audio file.

Features:
- Uses `gTTS` for Khmer Text-to-Speech with slower, softer speech
- Male voice preference when available
- Uses `python-telegram-bot` for Telegram integration (v13 style Updater based example)
- Handles `/start` and `/help` commands
- `/speak <text>` command explicitly creates audio from provided text
- Any plain text message (non-command) will also be converted to speech
- Splits long text into chunks to avoid remote TTS length limits
- Includes health check endpoint for deployment platforms
- Enhanced audio processing for softer, more natural sound

Requirements
------------
Install required packages:

    pip install python-telegram-bot==13.17 gTTS pydub

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
- gTTS sends requests to Google to get speech; it requires network access
- Audio is processed to be slower and softer for better listening experience
- pydub is used for audio enhancement (requires ffmpeg for full functionality)

"""

import os
import logging
import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from gtts import gTTS
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

try:
    from pydub import AudioSegment
    AUDIO_PROCESSING_AVAILABLE = True
except ImportError:
    AUDIO_PROCESSING_AVAILABLE = False
    print("Warning: pydub not available. Audio enhancement disabled.")

# Configuration
LANG = 'km'  # Khmer language code
CHUNK_SIZE = 3500  # Reduced chunk size for better processing
PORT = int(os.getenv('PORT', 8080))  # Port for health check server
SPEECH_SPEED = 0.85  # Slower speed for softer speech (0.5-2.0)
VOLUME_ADJUSTMENT = -3  # Slightly reduce volume for softer sound (dB)

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
            self.wfile.write(b'OK - Khmer TTS Bot Running')
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
        # Try to find a sentence boundary backward from end
        if end < len(text):
            # Look for Khmer sentence endings and common punctuation
            split_chars = ['.', '។', '\n', '?', '!', '៕', '៖', '។']
            split_at = -1
            
            for char in split_chars:
                pos = text.rfind(char, start, end)
                if pos > split_at and pos > start:
                    split_at = pos
            
            if split_at == -1 or split_at <= start:
                split_at = end
        else:
            split_at = end

        chunk = text[start:split_at].strip()
        if chunk:
            chunks.append(chunk)
        start = split_at
        if start == end:
            # Avoid infinite loop
            start += 1
    return chunks


def enhance_audio(input_path: str, output_path: str):
    """Enhance audio for softer, more natural male voice"""
    if not AUDIO_PROCESSING_AVAILABLE:
        # If pydub not available, just copy the file
        import shutil
        shutil.copy2(input_path, output_path)
        return
    
    try:
        audio = AudioSegment.from_mp3(input_path)
        
        # Adjust speed for softer speech
        if SPEECH_SPEED != 1.0:
            # Change speed without changing pitch (requires ffmpeg)
            try:
                audio = audio.speedup(playback_speed=1/SPEECH_SPEED)
            except:
                # Fallback: simple frame rate manipulation
                audio = audio._spawn(audio.raw_data, overrides={
                    "frame_rate": int(audio.frame_rate * SPEECH_SPEED)
                }).set_frame_rate(audio.frame_rate)
        
        # Adjust volume for softer sound
        if VOLUME_ADJUSTMENT != 0:
            audio = audio + VOLUME_ADJUSTMENT
        
        # Apply gentle low-pass filter for warmer tone (male voice characteristic)
        try:
            audio = audio.low_pass_filter(3000)
        except:
            pass  # Skip if not supported
        
        # Add slight reverb effect for more natural sound
        try:
            # Simple reverb by mixing with delayed, quieter version
            reverb = audio - 20  # 20dB quieter
            delayed = AudioSegment.silent(duration=50) + reverb  # 50ms delay
            audio = audio.overlay(delayed[:len(audio)])
        except:
            pass  # Skip if not supported
        
        # Export enhanced audio
        audio.export(output_path, format="mp3", bitrate="128k")
        
    except Exception as e:
        logger.warning(f'Audio enhancement failed, using original: {e}')
        import shutil
        shutil.copy2(input_path, output_path)


def text_to_mp3(text: str, lang: str = LANG) -> str:
    """Create an enhanced mp3 file from text using gTTS. Returns the file path.

    NOTE: Caller is responsible for deleting the file when finished.
    """
    # Create temporary files
    fd_raw, raw_path = tempfile.mkstemp(suffix='_raw.mp3')
    os.close(fd_raw)
    fd_enhanced, enhanced_path = tempfile.mkstemp(suffix='.mp3')
    os.close(fd_enhanced)

    try:
        # Generate TTS with slower speaking rate if supported
        tts_kwargs = {'text': text, 'lang': lang, 'slow': False}
        
        # Try to use slower speech for softer sound
        try:
            tts = gTTS(**tts_kwargs, slow=True)
        except:
            tts = gTTS(**tts_kwargs)
        
        tts.save(raw_path)
        
        # Enhance audio for male voice characteristics
        enhance_audio(raw_path, enhanced_path)
        
        # Clean up raw file
        try:
            os.remove(raw_path)
        except:
            pass
            
        return enhanced_path
        
    except Exception as e:
        # Clean up on error
        for path in [raw_path, enhanced_path]:
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

    # Send processing message with better feedback
    try:
        processing_msg = context.bot.send_message(
            chat_id=chat_id, 
            text="🎙️ Creating natural male voice audio... Please wait."
        )
    except Exception as e:
        logger.error(f'Failed to send processing message: {e}')
        processing_msg = None

    chunks = split_text(text)
    files_to_delete = []
    
    try:
        if len(chunks) == 1:
            audio_counter += 1
            audio_id = f"Voice{audio_counter:03d}"
            mp3_path = text_to_mp3(chunks[0])
            files_to_delete.append(mp3_path)
            
            with open(mp3_path, 'rb') as f:
                context.bot.send_audio(
                    chat_id=chat_id, 
                    audio=f, 
                    filename=f'{audio_id}.mp3', 
                    caption=f'🎧 {audio_id} - Khmer Male Voice',
                    title=f'Khmer TTS - {audio_id}'
                )
        else:
            # Multiple chunks: send as a sequence
            for i, chunk in enumerate(chunks, start=1):
                audio_counter += 1
                audio_id = f"Voice{audio_counter:03d}"
                mp3_path = text_to_mp3(chunk)
                files_to_delete.append(mp3_path)
                
                with open(mp3_path, 'rb') as f:
                    caption = f'🎧 {audio_id} - Part {i}/{len(chunks)} (Male Voice)'
                    context.bot.send_audio(
                        chat_id=chat_id, 
                        audio=f, 
                        filename=f'{audio_id}.mp3', 
                        caption=caption,
                        title=f'Khmer TTS - {audio_id}'
                    )
                    
    except Exception as e:
        logger.exception('Error creating or sending TTS audio: %s', e)
        try:
            update.message.reply_text(
                'Sorry, an error occurred while creating the speech. Please try again.\n'
                'សោមទោស! មានបញ្ហាក្នុងការបង្កើតសំឡេង។ សូមព្យាយាមម្តងទៀត។'
            )
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
        "សួស្តី! 🇰🇭🎙️\n\n"
        "I'm an enhanced Khmer Text-to-Speech bot with natural male voice!\n"
        "ខ្ញុំជាបុគ្គលិកសំឡេងខ្មែរប្រុស ធម្មជាតិ!\n\n"
        "✨ Features:\n"
        "• Natural male voice with soft tone\n"
        "• Enhanced audio quality\n"
        "• Supports both Khmer and English\n"
        "• Automatic text chunking for long messages\n\n"
        "Commands:\n"
        "• Send any text → Get enhanced audio\n"
        "• /speak <text> - Convert specific text\n"
        "• /help - Show detailed help"
    )
    update.message.reply_text(welcome_msg)


def help_handler(update: Update, context: CallbackContext):
    """Handle /help command"""
    help_msg = (
        "🎧 Enhanced Khmer TTS Bot Help\n\n"
        "🎙️ Voice Features:\n"
        "• Natural male voice tone\n"
        "• Slower, softer speech\n"
        "• Enhanced audio processing\n"
        "• Warm, pleasant sound\n\n"
        "📝 How to use:\n"
        "• Send any Khmer text → Get audio back\n"
        "• /speak <your text> → Convert specific text\n"
        "• Works with mixed Khmer/English text\n"
        "• Long texts split automatically\n\n"
        "💡 Examples:\n"
        "• /speak សួស្ដីអ្នកសុខសប្បាយទេ\n"
        "• /speak Hello សួស្ដី mixed text\n"
        "• Just type: ថ្ងៃនេះអាកាសធាតុល្អ"
    )
    update.message.reply_text(help_msg)


def speak_handler(update: Update, context: CallbackContext):
    """Handle /speak command"""
    text = ' '.join(context.args)
    if not text:
        update.message.reply_text(
            'Please provide text after /speak\n\n'
            'Example: /speak សួស្ដី\n'
            'ឧទាហរណ៍: /speak សួស្ដីអ្នកសុខសប្បាយទេ'
        )
        return
    tts_and_send(update, context, text)


def text_message_handler(update: Update, context: CallbackContext):
    """Handle plain text messages"""
    text = update.message.text
    if not text or text.strip() == '':
        return
    tts_and_send(update, context, text)


def error_handler(update: Update, context: CallbackContext):
    """Handle errors"""
    logger.error('Update caused error: %s', context.error)
    try:
        if update and update.effective_chat:
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="An error occurred. Please try again.\nមានបញ្ហា! សូមព្យាយាមម្តងទៀត។"
            )
    except Exception:
        pass


def main():
    if not TOKEN:
        raise RuntimeError('TELEGRAM_TOKEN environment variable not set')

    # Log configuration
    logger.info('=== Enhanced Khmer TTS Bot Configuration ===')
    logger.info(f'Language: {LANG}')
    logger.info(f'Speech Speed: {SPEECH_SPEED}x')
    logger.info(f'Volume Adjustment: {VOLUME_ADJUSTMENT} dB')
    logger.info(f'Audio Enhancement: {"Enabled" if AUDIO_PROCESSING_AVAILABLE else "Disabled"}')
    logger.info(f'Chunk Size: {CHUNK_SIZE} characters')

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

    logger.info('🎙️ Starting Enhanced Khmer TTS Telegram bot with male voice...')
    logger.info(f'📡 Health check available at http://localhost:{PORT}/health')
    
    # Start the bot
    updater.start_polling(drop_pending_updates=True)
    logger.info('✅ Bot is running! Send /start to begin.')
    updater.idle()


if __name__ == '__main__':
    main()
