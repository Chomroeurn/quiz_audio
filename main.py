"""
Enhanced Khmer TTS Telegram Bot
===============================

This bot supports both Khmer and English text-to-speech with natural speech processing.

Features:
- Auto-detects Khmer and English text
- Handles mixed language content intelligently
- Natural speech preprocessing (punctuation, numbers, etc.)
- Improved text chunking for better flow
- Better audio quality with optimized settings

Requirements:
- pip install python-telegram-bot==13.17 gTTS langdetect

Environment:
- Set TELEGRAM_TOKEN environment variable
"""

import os
import logging
import tempfile
import threading
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from gtts import gTTS
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# Try to import langdetect for language detection
try:
    from langdetect import detect, LangDetectError
    LANG_DETECT_AVAILABLE = True
except ImportError:
    LANG_DETECT_AVAILABLE = False
    print("Warning: langdetect not installed. Install with: pip install langdetect")

# Configuration
KHMER_LANG = 'km'
ENGLISH_LANG = 'en'
CHUNK_SIZE = 3000  # Reduced for better speech flow
PORT = int(os.getenv('PORT', 8080))

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
        pass


def start_health_check_server():
    """Start a simple HTTP server for health checks"""
    try:
        server = HTTPServer(('0.0.0.0', PORT), HealthCheckHandler)
        logger.info(f'Health check server started on port {PORT}')
        server.serve_forever()
    except Exception as e:
        logger.error(f'Failed to start health check server: {e}')


def detect_language(text: str) -> str:
    """Detect the primary language of the text"""
    if not LANG_DETECT_AVAILABLE:
        # Fallback: simple heuristic
        khmer_chars = len(re.findall(r'[\u1780-\u17FF]', text))
        english_chars = len(re.findall(r'[a-zA-Z]', text))
        
        if khmer_chars > english_chars:
            return KHMER_LANG
        else:
            return ENGLISH_LANG
    
    try:
        detected = detect(text)
        # Map detected language to supported languages
        if detected == 'km':
            return KHMER_LANG
        elif detected in ['en', 'es', 'fr', 'de', 'it']:  # gTTS supports these well
            return ENGLISH_LANG
        else:
            # For mixed or uncertain content, check character distribution
            khmer_chars = len(re.findall(r'[\u1780-\u17FF]', text))
            if khmer_chars > 10:  # If significant Khmer content
                return KHMER_LANG
            return ENGLISH_LANG
    except (LangDetectError, Exception):
        # Fallback to character-based detection
        khmer_chars = len(re.findall(r'[\u1780-\u17FF]', text))
        english_chars = len(re.findall(r'[a-zA-Z]', text))
        
        if khmer_chars > english_chars:
            return KHMER_LANG
        else:
            return ENGLISH_LANG


def preprocess_text_for_speech(text: str, lang: str) -> str:
    """Preprocess text to make it sound more natural when spoken"""
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text.strip())
    
    # Handle common abbreviations and make them speakable
    if lang == ENGLISH_LANG:
        # Expand common abbreviations
        text = re.sub(r'\bDr\.', 'Doctor', text)
        text = re.sub(r'\bMr\.', 'Mister', text)
        text = re.sub(r'\bMrs\.', 'Missus', text)
        text = re.sub(r'\bMs\.', 'Miss', text)
        text = re.sub(r'\betc\.', 'etcetera', text)
        text = re.sub(r'\bi\.e\.', 'that is', text)
        text = re.sub(r'\be\.g\.', 'for example', text)
        text = re.sub(r'\bvs\.', 'versus', text)
        
        # Handle numbers with ordinal indicators
        text = re.sub(r'(\d+)st\b', r'\1st', text)
        text = re.sub(r'(\d+)nd\b', r'\1nd', text)
        text = re.sub(r'(\d+)rd\b', r'\1rd', text)
        text = re.sub(r'(\d+)th\b', r'\1th', text)
        
        # Handle time format
        text = re.sub(r'(\d{1,2}):(\d{2})', r'\1 \2', text)
        
    # Handle URLs and make them more speakable
    text = re.sub(r'https?://[^\s]+', 'web link', text)
    text = re.sub(r'www\.[^\s]+', 'website', text)
    
    # Handle email addresses
    text = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', 'email address', text)
    
    # Clean up multiple punctuation
    text = re.sub(r'[.]{3,}', '...', text)
    text = re.sub(r'[!]{2,}', '!', text)
    text = re.sub(r'[?]{2,}', '?', text)
    
    # Add pauses for better speech flow
    text = re.sub(r'([.!?])\s*', r'\1 ', text)
    text = re.sub(r'([,;:])\s*', r'\1 ', text)
    
    return text.strip()


def smart_split_text(text: str, chunk_size: int = CHUNK_SIZE) -> list:
    """
    Intelligently split text for natural speech, preserving meaning and flow
    """
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    sentences = re.split(r'([.!?]+\s*)', text)
    
    current_chunk = ""
    
    for i in range(0, len(sentences), 2):
        if i + 1 < len(sentences):
            sentence = sentences[i] + sentences[i + 1]
        else:
            sentence = sentences[i]
        
        sentence = sentence.strip()
        if not sentence:
            continue
            
        # If adding this sentence would exceed chunk size
        if current_chunk and len(current_chunk + " " + sentence) > chunk_size:
            # Save current chunk and start new one
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = sentence
        else:
            # Add to current chunk
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence
    
    # Add final chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    # If we still have chunks that are too long, split them further
    final_chunks = []
    for chunk in chunks:
        if len(chunk) <= chunk_size:
            final_chunks.append(chunk)
        else:
            # Split on commas or other natural breaks
            sub_chunks = re.split(r'([,;]\s*)', chunk)
            current_sub = ""
            
            for j in range(0, len(sub_chunks), 2):
                if j + 1 < len(sub_chunks):
                    part = sub_chunks[j] + sub_chunks[j + 1]
                else:
                    part = sub_chunks[j]
                
                if current_sub and len(current_sub + part) > chunk_size:
                    if current_sub.strip():
                        final_chunks.append(current_sub.strip())
                    current_sub = part
                else:
                    current_sub += part
            
            if current_sub.strip():
                final_chunks.append(current_sub.strip())
    
    return [chunk for chunk in final_chunks if chunk.strip()]


def text_to_mp3(text: str, lang: str) -> str:
    """Create an mp3 file from text using gTTS with optimized settings"""
    fd, path = tempfile.mkstemp(suffix='.mp3')
    os.close(fd)

    try:
        # Preprocess text for natural speech
        processed_text = preprocess_text_for_speech(text, lang)
        
        # Create TTS with slow=False for more natural speed
        tts = gTTS(text=processed_text, lang=lang, slow=False)
        tts.save(path)
        return path
    except Exception as e:
        # Clean up on error
        try:
            os.remove(path)
        except:
            pass
        raise e


def handle_mixed_language_text(text: str) -> list:
    """
    Handle text that might contain both Khmer and English
    Returns list of (text_chunk, language) tuples
    """
    # Simple approach: split by language blocks
    # This is a basic implementation - could be enhanced further
    
    chunks = []
    current_chunk = ""
    current_lang = None
    
    # Split into words/phrases and detect language for each
    words = re.split(r'(\s+)', text)
    
    for word in words:
        if not word.strip():
            if current_chunk:
                current_chunk += word
            continue
            
        # Detect language of current word
        if re.search(r'[\u1780-\u17FF]', word):
            word_lang = KHMER_LANG
        else:
            word_lang = ENGLISH_LANG
        
        # If language changed or chunk getting too long
        if current_lang and (word_lang != current_lang or len(current_chunk + word) > CHUNK_SIZE):
            if current_chunk.strip():
                chunks.append((current_chunk.strip(), current_lang))
            current_chunk = word
            current_lang = word_lang
        else:
            current_chunk += word
            if current_lang is None:
                current_lang = word_lang
    
    # Add final chunk
    if current_chunk.strip():
        chunks.append((current_chunk.strip(), current_lang))
    
    # If no language switching detected, use overall detection
    if len(chunks) <= 1:
        detected_lang = detect_language(text)
        return [(text, detected_lang)]
    
    return chunks


def tts_and_send(update: Update, context: CallbackContext, text: str):
    global audio_counter
    
    chat_id = update.effective_chat.id
    user = update.effective_user
    logger.info('TTS request from user=%s chat_id=%s len=%d', user and user.username, chat_id, len(text))

    # Send processing message
    try:
        processing_msg = context.bot.send_message(
            chat_id=chat_id, 
            text="🎵 Processing your text... Please wait.\n🔊 Preparing natural speech..."
        )
    except Exception as e:
        logger.error(f'Failed to send processing message: {e}')
        processing_msg = None

    files_to_delete = []
    
    try:
        # Handle mixed language content
        language_chunks = handle_mixed_language_text(text)
        
        total_parts = 0
        all_audio_parts = []
        
        # Process each language chunk
        for chunk_text, lang in language_chunks:
            text_chunks = smart_split_text(chunk_text)
            
            for text_chunk in text_chunks:
                total_parts += 1
                audio_counter += 1
                audio_id = f"Gyn{audio_counter:02d}"
                
                mp3_path = text_to_mp3(text_chunk, lang)
                files_to_delete.append(mp3_path)
                
                lang_flag = "🇰🇭" if lang == KHMER_LANG else "🇺🇸"
                all_audio_parts.append((mp3_path, audio_id, lang_flag))
        
        # Send all audio parts
        for i, (mp3_path, audio_id, lang_flag) in enumerate(all_audio_parts, 1):
            with open(mp3_path, 'rb') as f:
                if total_parts == 1:
                    caption = f'🎧 {audio_id} {lang_flag} - Natural TTS'
                else:
                    caption = f'🎧 {audio_id} {lang_flag} - Part {i}/{total_parts}'
                
                context.bot.send_audio(
                    chat_id=chat_id,
                    audio=f,
                    filename=f'{audio_id}.mp3',
                    caption=caption
                )
                    
    except Exception as e:
        logger.exception('Error creating or sending TTS audio: %s', e)
        try:
            error_msg = 'Sorry, an error occurred while creating the speech. Please try again.'
            if "No text to send to TTS" in str(e):
                error_msg = 'The text appears to be empty or contains only special characters. Please try with different text.'
            update.message.reply_text(error_msg)
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
        "សួស្តី! 🇰🇭 Hello! 🇺🇸\n\n"
        "I'm an enhanced Khmer-English Text-to-Speech bot with natural voice!\n\n"
        "✨ Features:\n"
        "• 🗣️ Natural speech processing\n"
        "• 🌐 Auto-detects Khmer & English\n"
        "• 🎯 Handles mixed language text\n"
        "• 🎵 Optimized for clear pronunciation\n\n"
        "Commands:\n"
        "• Send any text for natural TTS\n"
        "• /speak <text> - Convert specific text\n"
        "• /help - Show detailed help\n\n"
        "Try: Hello សួស្តី how are you?"
    )
    update.message.reply_text(welcome_msg)


def help_handler(update: Update, context: CallbackContext):
    """Handle /help command"""
    help_msg = (
        "🎧 Enhanced Khmer-English TTS Bot\n\n"
        "🌟 Advanced Features:\n"
        "• 🤖 Smart language detection\n"
        "• 🎭 Natural speech preprocessing\n"
        "• 📝 Handles abbreviations & numbers\n"
        "• 🔄 Mixed language support\n"
        "• ⚡ Optimized chunking for flow\n\n"
        "📖 Usage Examples:\n"
        "• Pure Khmer: សួស្ដីអ្នកសុខសប្បាយទេ\n"
        "• Pure English: Hello, how are you today?\n"
        "• Mixed: Hello សួស្តី nice to meet you\n"
        "• With numbers: Today is January 1st, 2024\n\n"
        "💡 Tips:\n"
        "• Use proper punctuation for natural pauses\n"
        "• Long texts will be in single continuous audio\n"
        "• Mixed languages use optimal single voice\n"
        "• Character count shown in caption"
    )
    update.message.reply_text(help_msg)


def speak_handler(update: Update, context: CallbackContext):
    """Handle /speak command"""
    text = ' '.join(context.args)
    if not text:
        update.message.reply_text(
            'Please provide text after /speak\n\n'
            'Examples:\n'
            '• /speak សួស្ដីអ្នកមានសុខភាពល្អទេ\n'
            '• /speak Hello, how are you?\n'
            '• /speak Hello សួស្តី mixed language'
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

    logger.info('Starting Enhanced Khmer-English TTS Telegram bot...')
    logger.info(f'Health check available at http://localhost:{PORT}/health')
    logger.info(f'Language detection: {"Available" if LANG_DETECT_AVAILABLE else "Basic fallback"}')
    
    # Start the bot
    updater.start_polling(drop_pending_updates=True)
    updater.idle()


if __name__ == '__main__':
    main()
