"""
Khmer TTS Telegram Bot - Stable Male Voice Version
==================================================

This bot converts Khmer text to speech and applies simple audio processing 
to make the voice sound more masculine through pitch adjustment.

Features:
- Uses `gTTS` for Khmer Text-to-Speech
- Simple but effective pitch lowering for male voice simulation
- Robust error handling and fallback mechanisms
- Works with just basic dependencies
- Enhanced with audio effects when possible

Requirements
------------
Required packages:
    pip install python-telegram-bot==13.17 gTTS pydub

Optional for better processing:
    pip install librosa soundfile numpy

Environment
-----------
    export TELEGRAM_TOKEN="123456:ABC-DEF..."

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

# Audio processing imports with graceful fallbacks
try:
    from pydub import AudioSegment
    from pydub.effects import normalize
    HAS_PYDUB = True
    print("✅ pydub loaded successfully")
except ImportError as e:
    HAS_PYDUB = False
    print(f"❌ pydub not available: {e}")

# Advanced processing (optional)
try:
    import librosa
    import soundfile as sf
    import numpy as np
    HAS_LIBROSA = True
    print("✅ librosa loaded successfully")
except ImportError:
    HAS_LIBROSA = False
    print("ℹ️ librosa not available (optional)")

# Configuration
LANG = 'km'
CHUNK_SIZE = 3000
PORT = int(os.getenv('PORT', 8080))

# Voice parameters (conservative settings for stability)
PITCH_REDUCTION = 0.8  # Simple pitch reduction factor
SPEED_FACTOR = 0.95    # Slightly slower
audio_counter = 0

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    logger.error('TELEGRAM_TOKEN environment variable not set!')
    sys.exit(1)


class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ['/health', '/']:
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            status = f"Male Voice TTS Bot - pydub:{HAS_PYDUB} librosa:{HAS_LIBROSA}"
            self.wfile.write(status.encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass


def start_health_check_server():
    try:
        server = HTTPServer(('0.0.0.0', PORT), HealthCheckHandler)
        logger.info(f'Health check server started on port {PORT}')
        server.serve_forever()
    except Exception as e:
        logger.error(f'Health check server error: {e}')


def split_text_safely(text: str, max_length: int = CHUNK_SIZE):
    """Safe text splitting with error handling"""
    try:
        if not text or len(text) <= max_length:
            return [text] if text else []
        
        chunks = []
        sentences = text.replace('។', '.|').replace('.', '.|').split('|')
        
        current_chunk = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            if len(current_chunk + sentence) <= max_length:
                current_chunk += sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        return chunks if chunks else [text]
        
    except Exception as e:
        logger.error(f"Text splitting error: {e}")
        return [text]  # Fallback to original text


def make_voice_masculine_simple(input_path: str, output_path: str):
    """Simple pitch lowering using pydub - most stable approach"""
    if not HAS_PYDUB:
        # No processing available, just copy
        import shutil
        shutil.copy2(input_path, output_path)
        return False
    
    try:
        # Load audio
        audio = AudioSegment.from_file(input_path)
        
        # Method 1: Frame rate manipulation (most reliable)
        # Lower the sample rate, then restore to original rate
        # This effectively lowers the pitch
        original_rate = audio.frame_rate
        new_rate = int(original_rate * PITCH_REDUCTION)
        
        # Create pitched version
        pitched_down = audio._spawn(
            audio.raw_data,
            overrides={"frame_rate": new_rate}
        ).set_frame_rate(original_rate)
        
        # Speed adjustment
        if SPEED_FACTOR != 1.0:
            # Adjust speed by changing frame rate slightly
            speed_rate = int(pitched_down.frame_rate * SPEED_FACTOR)
            speed_adjusted = pitched_down._spawn(
                pitched_down.raw_data,
                overrides={"frame_rate": speed_rate}
            ).set_frame_rate(pitched_down.frame_rate)
        else:
            speed_adjusted = pitched_down
        
        # Simple EQ: boost lower frequencies, reduce higher ones
        try:
            # Split into frequency bands and adjust
            low_freq = speed_adjusted.low_pass_filter(800).apply_gain(2)  # Boost bass
            high_freq = speed_adjusted.high_pass_filter(800).apply_gain(-1)  # Reduce treble
            final_audio = low_freq.overlay(high_freq)
        except:
            final_audio = speed_adjusted  # Skip EQ if it fails
        
        # Normalize and export
        try:
            final_audio = normalize(final_audio)
        except:
            pass  # Skip normalization if it fails
        
        final_audio.export(output_path, format="mp3", bitrate="128k")
        logger.info("✅ Simple male voice processing completed")
        return True
        
    except Exception as e:
        logger.error(f"Simple processing failed: {e}")
        # Fallback: copy original file
        try:
            import shutil
            shutil.copy2(input_path, output_path)
        except:
            pass
        return False


def make_voice_masculine_advanced(input_path: str, output_path: str):
    """Advanced processing with librosa (if available)"""
    if not HAS_LIBROSA:
        return False
    
    try:
        # Load audio
        y, sr = librosa.load(input_path, sr=None)
        
        # Pitch shift down
        y_shifted = librosa.effects.pitch_shift(y, sr=sr, n_steps=-3)
        
        # Time stretch for speed
        if SPEED_FACTOR != 1.0:
            y_final = librosa.effects.time_stretch(y_shifted, rate=1/SPEED_FACTOR)
        else:
            y_final = y_shifted
        
        # Save
        sf.write(output_path, y_final, sr)
        logger.info("✅ Advanced male voice processing completed")
        return True
        
    except Exception as e:
        logger.error(f"Advanced processing failed: {e}")
        return False


def create_male_voice_tts(text: str) -> str:
    """Create male-sounding TTS with robust error handling"""
    # Create temp files
    original_path = None
    processed_path = None
    
    try:
        # Create temporary files
        fd1, original_path = tempfile.mkstemp(suffix='_orig.mp3')
        os.close(fd1)
        fd2, processed_path = tempfile.mkstemp(suffix='_male.mp3')
        os.close(fd2)
        
        # Generate TTS
        logger.info(f"Generating TTS for: {text[:50]}...")
        tts = gTTS(text=text, lang=LANG, slow=False)
        tts.save(original_path)
        logger.info("✅ TTS generation completed")
        
        # Try advanced processing first
        success = False
        if HAS_LIBROSA:
            success = make_voice_masculine_advanced(original_path, processed_path)
        
        # Fall back to simple processing
        if not success:
            success = make_voice_masculine_simple(original_path, processed_path)
        
        if not success:
            logger.warning("Voice processing failed, using original")
            # Use original file
            import shutil
            shutil.copy2(original_path, processed_path)
        
        # Clean up original
        try:
            os.remove(original_path)
        except:
            pass
            
        return processed_path
        
    except Exception as e:
        logger.error(f"TTS creation failed: {e}")
        # Clean up on error
        for path in [original_path, processed_path]:
            if path:
                try:
                    os.remove(path)
                except:
                    pass
        raise


def send_tts_audio(update: Update, context: CallbackContext, text: str):
    """Main TTS function with comprehensive error handling"""
    global audio_counter
    
    if not text or not text.strip():
        update.message.reply_text("Please provide some text to convert.")
        return
    
    chat_id = update.effective_chat.id
    user = update.effective_user
    username = user.username if user else "Unknown"
    
    logger.info(f'🎙️ TTS request from {username}, chat {chat_id}, length {len(text)}')
    
    # Send processing message
    processing_msg = None
    try:
        processing_type = "Advanced" if HAS_LIBROSA else "Basic" if HAS_PYDUB else "Standard"
        processing_msg = context.bot.send_message(
            chat_id=chat_id,
            text=f"🎙️ Creating male voice audio ({processing_type})...\nProcessing your text, please wait."
        )
    except Exception as e:
        logger.error(f"Failed to send processing message: {e}")
    
    # Split text and process
    chunks = split_text_safely(text)
    files_to_cleanup = []
    
    try:
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
                
            audio_counter += 1
            audio_id = f"MaleVoice{audio_counter:03d}"
            
            try:
                # Create the audio file
                audio_path = create_male_voice_tts(chunk)
                files_to_cleanup.append(audio_path)
                
                # Send audio
                with open(audio_path, 'rb') as audio_file:
                    caption = f"🎧 {audio_id}"
                    if len(chunks) > 1:
                        caption += f" - Part {i+1}/{len(chunks)}"
                    
                    processing_info = "Advanced" if HAS_LIBROSA else "Enhanced" if HAS_PYDUB else "Standard"
                    caption += f" ({processing_info})"
                    
                    context.bot.send_audio(
                        chat_id=chat_id,
                        audio=audio_file,
                        filename=f'{audio_id}.mp3',
                        caption=caption,
                        title=f'Khmer Male Voice - {audio_id}',
                        performer='Khmer TTS Bot'
                    )
                    
            except Exception as e:
                logger.error(f"Failed to process chunk {i+1}: {e}")
                context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Failed to process part {i+1}. Skipping..."
                )
                continue
        
        logger.info(f"✅ Successfully processed {len(chunks)} chunks")
        
    except Exception as e:
        logger.error(f"TTS processing failed: {e}")
        try:
            context.bot.send_message(
                chat_id=chat_id,
                text="❌ Sorry, there was an error creating the audio. Please try again.\n"
                     "សោមទោស! មានបញ្ហាក្នុងការបង្កើតសំឡេង។ សូមព្យាយាមម្តងទៀត។"
            )
        except:
            pass
    
    finally:
        # Cleanup
        for file_path in files_to_cleanup:
            try:
                os.remove(file_path)
            except:
                pass
        
        # Delete processing message
        if processing_msg:
            try:
                context.bot.delete_message(chat_id=chat_id, message_id=processing_msg.message_id)
            except:
                pass


# Command handlers
def start_command(update: Update, context: CallbackContext):
    processing_type = "Advanced" if HAS_LIBROSA else "Enhanced" if HAS_PYDUB else "Basic"
    
    welcome = (
        "សួស្តី! 🇰🇭👨\n\n"
        f"🎙️ Khmer Male Voice TTS Bot ({processing_type} Mode)\n\n"
        "I convert Khmer text to speech with masculine voice characteristics!\n\n"
        "Features:\n"
        "• Lower pitch for male voice\n"
        "• Enhanced bass frequencies\n"
        "• Optimized speech speed\n"
        "• Supports long text (auto-split)\n\n"
        "Usage:\n"
        "• Send any Khmer text directly\n"
        "• /speak <text> - Convert specific text\n"
        "• /help - More information"
    )
    
    if not HAS_PYDUB:
        welcome += "\n\n💡 Install pydub for voice enhancement:\npip install pydub"
    
    update.message.reply_text(welcome)


def help_command(update: Update, context: CallbackContext):
    help_text = (
        "🎧 Khmer Male Voice TTS Help\n\n"
        "🎙️ Voice Processing:\n"
        f"• Mode: {'Advanced' if HAS_LIBROSA else 'Enhanced' if HAS_PYDUB else 'Basic'}\n"
        "• Pitch lowering for masculine tone\n"
        "• Bass boost and treble reduction\n"
        "• Speed optimization\n\n"
        "📝 Commands:\n"
        "• Send text directly → Auto conversion\n"
        "• /speak <text> → Convert specific text\n"
        "• /help → This help\n\n"
        "Examples:\n"
        "• សួស្ដីអ្នកសុខសប្បាយទេ\n"
        "• /speak ថ្ងៃនេះអាកាសធាតុល្អ\n"
        "• Mixed English និង Khmer text\n\n"
    )
    
    if not HAS_LIBROSA and HAS_PYDUB:
        help_text += "🔧 For best quality:\npip install librosa soundfile\n\n"
    elif not HAS_PYDUB:
        help_text += "🔧 For voice enhancement:\npip install pydub librosa soundfile\n\n"
    
    help_text += "Note: Processing may take 10-30 seconds depending on text length."
    
    update.message.reply_text(help_text)


def speak_command(update: Update, context: CallbackContext):
    text = ' '.join(context.args)
    if not text:
        update.message.reply_text(
            "Please provide text after /speak\n\n"
            "Example: /speak សួស្ដីអ្នកសុខសប្បាយទេ"
        )
        return
    send_tts_audio(update, context, text)


def text_message_handler(update: Update, context: CallbackContext):
    text = update.message.text
    if text and text.strip():
        send_tts_audio(update, context, text.strip())


def error_handler(update: Update, context: CallbackContext):
    logger.error(f'Update {update} caused error {context.error}')


def main():
    logger.info("=" * 50)
    logger.info("🎙️ KHMER MALE VOICE TTS BOT")
    logger.info("=" * 50)
    logger.info(f"Dependencies - pydub: {HAS_PYDUB}, librosa: {HAS_LIBROSA}")
    logger.info(f"Processing mode: {'Advanced' if HAS_LIBROSA else 'Enhanced' if HAS_PYDUB else 'Basic'}")
    logger.info(f"Pitch reduction: {PITCH_REDUCTION}")
    logger.info(f"Speed factor: {SPEED_FACTOR}")
    
    # Start health check
    health_thread = threading.Thread(target=start_health_check_server, daemon=True)
    health_thread.start()
    
    # Setup bot
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Add handlers
    dp.add_handler(CommandHandler('start', start_command))
    dp.add_handler(CommandHandler('help', help_command))
    dp.add_handler(CommandHandler('speak', speak_command))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, text_message_handler))
    dp.add_error_handler(error_handler)
    
    logger.info("🚀 Starting bot...")
    logger.info(f"📡 Health check: http://localhost:{PORT}/health")
    
    try:
        updater.start_polling(drop_pending_updates=True)
        logger.info("✅ Bot started successfully! Send /start to test.")
        updater.idle()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise


if __name__ == '__main__':
    main()
