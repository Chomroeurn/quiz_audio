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
                # Send audio with original text in caption
                caption = f'🎧 {audio_id} - Khmer TTS\n\n📝 Original text: {text}'
                context.bot.send_audio(
                    chat_id=chat_id, 
                    audio=f, 
                    filename=f'{audio_id}.mp3', 
                    caption=caption
                )
        else:
            # Multiple chunks: send as a sequence of audios
            # First, send the original text
            context.bot.send_message(
                chat_id=chat_id, 
                text=f'📝 Original text: {text}\n\n🎵 Converting to {len(chunks)} audio parts...'
            )
            
            for i, chunk in enumerate(chunks, start=1):
                audio_counter += 1
                audio_id = f"Gyn{audio_counter:02d}"
                mp3_path = text_to_mp3(chunk)
                files_to_delete.append(mp3_path)
                
                with open(mp3_path, 'rb') as f:
                    caption = f'🎧 {audio_id} - Part {i}/{len(chunks)}\n\n📝 Text: {chunk}'
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
