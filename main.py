"""
Khmer TTS Telegram Bot - Enhanced with Voice Manipulation for Male Sound
========================================================================

This bot converts Khmer text to speech and applies audio processing to make the female voice
sound more masculine through pitch shifting and formant manipulation.

Features:
- Uses `gTTS` for Khmer Text-to-Speech (female voice base)
- Applies pitch shifting and audio processing to simulate male voice
- Advanced audio manipulation using `pydub` and `librosa`
- Telegram integration with enhanced user experience
- Automatic text chunking for long messages
- Health check endpoint for deployment

Requirements
------------
Install required packages:

    pip install python-telegram-bot==13.17 gTTS pydub librosa soundfile numpy

For full audio processing capabilities, also install:
- FFmpeg (system package)
- SoX (optional, for advanced audio effects)

Environment
-----------
Set your Telegram Bot Token:

    export TELEGRAM_TOKEN="123456:ABC-DEF..."

Usage
-----

    python khmer_tts_telegram_bot.py

Audio Processing Notes
---------------------
- Base female voice is pitch-shifted down to simulate male voice
- Formant frequencies are adjusted for masculine characteristics  
- Speed and tone are modified for more natural male sound
- Processing may take longer but results in more convincing male voice

"""

import os
import logging
import tempfile
import threading
import numpy as np
from http.server import HTTPServer, BaseHTTPRequestHandler
from gtts import gTTS
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# Advanced audio processing imports
try:
    from pydub import AudioSegment
    from pydub.effects import normalize
    import librosa
    import soundfile as sf
    ADVANCED_PROCESSING = True
    print("✅ Advanced audio processing enabled (pydub + librosa)")
except ImportError as e:
    ADVANCED_PROCESSING = False
    print(f"⚠️  Advanced processing disabled. Missing: {e}")
    print("Install with: pip install pydub librosa soundfile numpy")
    # Basic fallback
    try:
        from pydub import AudioSegment
        BASIC_PROCESSING = True
    except ImportError:
        BASIC_PROCESSING = False

# Configuration for male voice simulation
LANG = 'km'  # Khmer language code
CHUNK_SIZE = 3000  # Smaller chunks for better processing
PORT = int(os.getenv('PORT', 8080))

# Voice masculinization parameters
PITCH_SHIFT_SEMITONES = -4  # Lower pitch by 4 semitones (more masculine)
FORMANT_SHIFT = 0.85        # Reduce formant frequencies (male characteristic)
SPEED_FACTOR = 0.90         # Slightly slower for masculine delivery
BASS_BOOST_DB = 3           # Boost low frequencies
TREBLE_CUT_DB = -2          # Reduce high frequencies

# Global counter
audio_counter = 0

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    logger.error('Please set the TELEGRAM_TOKEN environment variable and restart the bot.')


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Health check handler"""
    def do_GET(self):
        if self.path == '/health' or self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            status = "Advanced" if ADVANCED_PROCESSING else "Basic" if BASIC_PROCESSING else "Limited"
            self.wfile.write(f'OK - Khmer Male Voice TTS Bot ({status} Processing)'.encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass


def start_health_check_server():
    """Start health check server"""
    try:
        server = HTTPServer(('0.0.0.0', PORT), HealthCheckHandler)
        logger.info(f'Health check server started on port {PORT}')
        server.serve_forever()
    except Exception as e:
        logger.error(f'Failed to start health check server: {e}')


def split_text(text: str, chunk_size: int = CHUNK_SIZE):
    """Split text intelligently on Khmer sentence boundaries"""
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    
    # Khmer and common sentence endings
    endings = ['.', '។', '\n', '?', '!', '៕', '៖', 'ៗ', ':', ';']
    
    while start < len(text):
        end = min(start + chunk_size, len(text))
        
        if end < len(text):
            # Find the best split point
            best_split = end
            for ending in endings:
                split_pos = text.rfind(ending, start, end)
                if split_pos > start:
                    best_split = split_pos + 1
                    break
            
            # If no good split found, try word boundary
            if best_split == end:
                space_pos = text.rfind(' ', start, end)
                if space_pos > start:
                    best_split = space_pos
        else:
            best_split = end

        chunk = text[start:best_split].strip()
        if chunk:
            chunks.append(chunk)
        
        start = best_split
        if start == end:
            start += 1  # Avoid infinite loop
            
    return chunks


def masculinize_voice_advanced(audio_file_path: str, output_path: str):
    """Advanced voice masculinization using librosa"""
    if not ADVANCED_PROCESSING:
        raise ImportError("Advanced processing not available")
    
    try:
        # Load audio file
        y, sr = librosa.load(audio_file_path, sr=None)
        
        # 1. Pitch shifting (lower pitch for male voice)
        y_shifted = librosa.effects.pitch_shift(y, sr=sr, n_steps=PITCH_SHIFT_SEMITONES)
        
        # 2. Formant shifting (simulate male vocal tract)
        # This is approximated by spectral envelope manipulation
        stft = librosa.stft(y_shifted)
        magnitude, phase = np.abs(stft), np.angle(stft)
        
        # Frequency axis manipulation for formant shifting
        freqs = librosa.fft_frequencies(sr=sr)
        formant_shifted_mag = np.zeros_like(magnitude)
        
        for i in range(magnitude.shape[1]):
            # Interpolate to shift formant frequencies
            freq_indices = np.arange(len(freqs)) * FORMANT_SHIFT
            freq_indices = np.clip(freq_indices, 0, len(freqs) - 1)
            
            # Linear interpolation for formant shifting
            for j, freq_idx in enumerate(freq_indices):
                if j < len(magnitude):
                    formant_shifted_mag[j, i] = np.interp(freq_idx, np.arange(len(freqs)), magnitude[:, i])
        
        # Reconstruct audio
        stft_modified = formant_shifted_mag * np.exp(1j * phase)
        y_formant = librosa.istft(stft_modified)
        
        # 3. Speed adjustment (slightly slower for masculine delivery)
        y_final = librosa.effects.time_stretch(y_formant, rate=1/SPEED_FACTOR)
        
        # 4. EQ adjustments (boost bass, reduce treble)
        # Apply simple filtering
        y_final = librosa.effects.preemphasis(y_final, coef=-0.1)  # Inverse preemphasis for bass boost
        
        # Save the processed audio
        sf.write(output_path, y_final, sr)
        
        logger.info("✅ Advanced voice masculinization completed")
        return True
        
    except Exception as e:
        logger.error(f"Advanced processing failed: {e}")
        return False


def masculinize_voice_basic(audio_file_path: str, output_path: str):
    """Basic voice masculinization using pydub"""
    try:
        audio = AudioSegment.from_file(audio_file_path)
        
        # 1. Lower the pitch (octave down is too much, so we use frame rate trick)
        # Reduce sample rate then restore (pitch shift effect)
        new_sample_rate = int(audio.frame_rate * 0.85)  # Lower pitch
        pitched_audio = audio._spawn(audio.raw_data, overrides={"frame_rate": new_sample_rate})
        pitched_audio = pitched_audio.set_frame_rate(audio.frame_rate)
        
        # 2. Speed adjustment
        if SPEED_FACTOR != 1.0:
            # Simple speed change by frame rate manipulation
            speed_audio = pitched_audio._spawn(
                pitched_audio.raw_data, 
                overrides={"frame_rate": int(pitched_audio.frame_rate * SPEED_FACTOR)}
            ).set_frame_rate(pitched_audio.frame_rate)
        else:
            speed_audio = pitched_audio
        
        # 3. EQ adjustments
        # Boost bass (low frequencies)
        bass_boosted = speed_audio.low_pass_filter(1000).apply_gain(BASS_BOOST_DB)
        mid_high = speed_audio.high_pass_filter(1000).apply_gain(TREBLE_CUT_DB)
        
        # Mix back together
        final_audio = bass_boosted.overlay(mid_high)
        
        # 4. Normalize and export
        final_audio = normalize(final_audio)
        final_audio.export(output_path, format="mp3", bitrate="128k")
        
        logger.info("✅ Basic voice masculinization completed")
        return True
        
    except Exception as e:
        logger.error(f"Basic processing failed: {e}")
        return False


def create_male_voice_tts(text: str, lang: str = LANG) -> str:
    """Create male-sounding TTS from text"""
    # Create temporary files
    fd_original, original_path = tempfile.mkstemp(suffix='_original.mp3')
    os.close(fd_original)
    fd_processed, processed_path = tempfile.mkstemp(suffix='_male.mp3')
    os.close(fd_processed)

    try:
        # Generate original TTS (female voice)
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save(original_path)
        
        # Apply voice masculinization
        success = False
        
        if ADVANCED_PROCESSING:
            success = masculinize_voice_advanced(original_path, processed_path)
        
        if not success and BASIC_PROCESSING:
            success = masculinize_voice_basic(original_path, processed_path)
        
        if not success:
            # Fallback: just copy original
            import shutil
            shutil.copy2(original_path, processed_path)
            logger.warning("Voice processing failed, using original female voice")
        
        # Clean up original
        try:
            os.remove(original_path)
        except:
            pass
            
        return processed_path
        
    except Exception as e:
        # Clean up on error
        for path in [original_path, processed_path]:
            try:
                os.remove(path)
            except:
                pass
        raise e


def tts_and_send(update: Update, context: CallbackContext, text: str):
    global audio_counter
    
    chat_id = update.effective_chat.id
    user = update.effective_user
    logger.info('🎙️ Male voice TTS request from user=%s chat_id=%s len=%d', 
                user and user.username, chat_id, len(text))

    # Processing message
    processing_type = "Advanced" if ADVANCED_PROCESSING else "Basic" if BASIC_PROCESSING else "Standard"
    try:
        processing_msg = context.bot.send_message(
            chat_id=chat_id, 
            text=f"🎙️ Creating male voice ({processing_type} processing)...\n"
                 f"This may take a moment for best quality."
        )
    except Exception as e:
        logger.error(f'Failed to send processing message: {e}')
        processing_msg = None

    chunks = split_text(text)
    files_to_delete = []
    
    try:
        total_chunks = len(chunks)
        
        for i, chunk in enumerate(chunks, start=1):
            audio_counter += 1
            audio_id = f"MaleVoice{audio_counter:03d}"
            
            # Create male voice audio
            mp3_path = create_male_voice_tts(chunk)
            files_to_delete.append(mp3_path)
            
            with open(mp3_path, 'rb') as f:
                if total_chunks == 1:
                    caption = f'🎧 {audio_id} - Khmer Male Voice ({processing_type})'
                else:
                    caption = f'🎧 {audio_id} - Part {i}/{total_chunks} ({processing_type})'
                
                context.bot.send_audio(
                    chat_id=chat_id, 
                    audio=f, 
                    filename=f'{audio_id}.mp3', 
                    caption=caption,
                    title=f'Khmer Male TTS - {audio_id}',
                    performer='Khmer TTS Bot'
                )
                    
    except Exception as e:
        logger.exception('Error creating male voice TTS: %s', e)
        try:
            error_msg = (
                'Sorry, an error occurred while creating the male voice. '
                'សោមទោស! មានបញ្ហាក្នុងការបង្កើតសំឡេងប្រុស។'
            )
            if not ADVANCED_PROCESSING:
                error_msg += '\n\n💡 Install librosa for better voice processing:\npip install librosa soundfile'
                
            update.message.reply_text(error_msg)
        except Exception:
            pass
    finally:
        # Clean up
        for path in files_to_delete:
            try:
                os.remove(path)
            except:
                pass
        
        # Delete processing message
        if processing_msg:
            try:
                context.bot.delete_message(chat_id=chat_id, message_id=processing_msg.message_id)
            except:
                pass


def start_handler(update: Update, context: CallbackContext):
    """Handle /start command"""
    processing_type = "Advanced" if ADVANCED_PROCESSING else "Basic" if BASIC_PROCESSING else "Standard"
    
    welcome_msg = (
        "សួស្តី! 🇰🇭👨‍💼\n\n"
        "I'm a Khmer Male Voice TTS bot! I convert the default female Khmer voice "
        "to sound more masculine through advanced audio processing.\n\n"
        f"🔧 Processing Mode: **{processing_type}**\n\n"
        "✨ Male Voice Features:\n"
        "• Pitch shifted down for masculine tone\n"
        "• Formant frequencies adjusted\n" + 
        ("• Advanced spectral processing\n" if ADVANCED_PROCESSING else "") +
        "• Bass boost & treble adjustment\n"
        "• Natural speed optimization\n\n"
        "📝 Usage:\n"
        "• Send any Khmer text → Get male voice audio\n"
        "• /speak <text> - Convert specific text\n"
        "• /help - Detailed help & tips"
    )
    
    if not ADVANCED_PROCESSING:
        welcome_msg += (
            "\n\n💡 **Pro Tip**: For best male voice quality, install:\n"
            "`pip install librosa soundfile numpy`"
        )
    
    update.message.reply_text(welcome_msg, parse_mode='Markdown')


def help_handler(update: Update, context: CallbackContext):
    """Handle /help command"""
    processing_type = "Advanced" if ADVANCED_PROCESSING else "Basic" if BASIC_PROCESSING else "Standard"
    
    help_msg = (
        f"🎧 Khmer Male Voice TTS Bot - {processing_type} Mode\n\n"
        "🎙️ **How it works:**\n"
        "1. Generate Khmer TTS (female base voice)\n"
        "2. Apply pitch shifting (lower frequency)\n"
        "3. Adjust formant frequencies (male characteristics)\n"
        "4. Enhance bass and reduce treble\n"
        "5. Optimize speed for masculine delivery\n\n"
        "📝 **Commands:**\n"
        "• Send text directly → Auto conversion\n"
        "• `/speak <text>` → Convert specific text\n"
        "• `/help` → This help message\n\n"
        "💡 **Examples:**\n"
        "• `សួស្ដីអ្នកសុខសប្បាយទេ`\n"
        "• `/speak ថ្ងៃនេះអាកាសធាតុល្អណាស់`\n"
        "• `Hello mixed ជាមួយ Khmer text`\n\n"
    )
    
    if not ADVANCED_PROCESSING:
        help_msg += (
            "🔧 **Upgrade Processing:**\n"
            "For best male voice quality:\n"
            "```\n"
            "pip install librosa soundfile numpy\n"
            "```\n"
            "Then restart the bot for advanced spectral processing!"
        )
    else:
        help_msg += (
            "✅ **Advanced Processing Active**\n"
            "You're getting the highest quality male voice simulation!"
        )
    
    update.message.reply_text(help_msg, parse_mode='Markdown')


def speak_handler(update: Update, context: CallbackContext):
    """Handle /speak command"""
    text = ' '.join(context.args)
    if not text:
        update.message.reply_text(
            '🎙️ Please provide text after /speak\n\n'
            '**Example:** `/speak សួស្ដីអ្នកសុខសប្បាយទេ`\n'
            '**ឧទាហរណ៍:** `/speak ថ្ងៃនេះអាកាសធាតុល្អ`',
            parse_mode='Markdown'
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
                text="❌ An error occurred. Please try again.\nមានបញ្ហា! សូមព្យាយាមម្តងទៀត។"
            )
    except:
        pass


def main():
    if not TOKEN:
        raise RuntimeError('TELEGRAM_TOKEN environment variable not set')

    # Configuration summary
    logger.info('=' * 50)
    logger.info('🎙️ KHMER MALE VOICE TTS BOT')
    logger.info('=' * 50)
    logger.info(f'Language: {LANG}')
    logger.info(f'Processing: {"Advanced (librosa)" if ADVANCED_PROCESSING else "Basic (pydub)" if BASIC_PROCESSING else "Limited"}')
    logger.info(f'Pitch Shift: {PITCH_SHIFT_SEMITONES} semitones')
    logger.info(f'Formant Shift: {FORMANT_SHIFT}x')
    logger.info(f'Speed Factor: {SPEED_FACTOR}x')
    logger.info(f'Bass Boost: +{BASS_BOOST_DB}dB')
    logger.info(f'Treble Cut: {TREBLE_CUT_DB}dB')
    logger.info('=' * 50)

    # Start health check server
    health_thread = threading.Thread(target=start_health_check_server, daemon=True)
    health_thread.start()

    # Set up bot
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Add handlers
    dp.add_handler(CommandHandler('start', start_handler))
    dp.add_handler(CommandHandler('help', help_handler))
    dp.add_handler(CommandHandler('speak', speak_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, text_message_handler))
    dp.add_error_handler(error_handler)

    logger.info('🚀 Starting Khmer Male Voice TTS Bot...')
    logger.info(f'📡 Health check: http://localhost:{PORT}/health')
    
    # Start the bot
    updater.start_polling(drop_pending_updates=True)
    logger.info('✅ Bot is running! Send /start to test the male voice.')
    updater.idle()


if __name__ == '__main__':
    main()
