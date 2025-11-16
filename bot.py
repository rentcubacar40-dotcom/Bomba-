import telebot
import requests
import tempfile
import os
import io
from urllib.parse import urlparse

BOT_TOKEN = "8200566220:AAH4Ld6dhXYxtdsph4s7SHyH2ficT0c3SLw"
bot = telebot.TeleBot(BOT_TOKEN)

THUMBNAIL_URL = "https://raw.githubusercontent.com/rentcubacar40-dotcom/telegram-file-bot/main/assets/foto.jpg"

def obtener_miniatura():
    try:
        response = requests.get(THUMBNAIL_URL, timeout=10)
        if response.status_code == 200:
            return io.BytesIO(response.content)
        return None
    except:
        return None

def descargar_archivo_desde_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=30, stream=True)
        response.raise_for_status()
        
        filename = "archivo_descargado"
        parsed = urlparse(url)
        path = parsed.path
        if '/' in path and '.' in path.split('/')[-1]:
            filename = path.split('/')[-1]
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)
            return temp_file.name, filename
        
    except Exception as e:
        return None, None

def enviar_archivo_con_thumbnail(chat_id, file_path, filename, url_original=None):
    try:
        with open(file_path, 'rb') as file:
            ext = os.path.splitext(filename)[1].lower()
            caption = f"📁 {filename}"
            if url_original:
                caption += f"\n🔗 {url_original}"
            
            thumbnail = obtener_miniatura()
            
            if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                bot.send_photo(chat_id, file, caption=caption)
            elif ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm']:
                if thumbnail:
                    bot.send_video(chat_id, file, caption=caption, thumbnail=thumbnail)
                else:
                    bot.send_video(chat_id, file, caption=caption)
            elif ext in ['.mp3', '.wav', '.ogg', '.m4a', '.flac']:
                if thumbnail:
                    bot.send_audio(chat_id, file, caption=caption, thumbnail=thumbnail)
                else:
                    bot.send_audio(chat_id, file, caption=caption)
            else:
                if thumbnail:
                    bot.send_document(chat_id, file, caption=caption, thumbnail=thumbnail)
                else:
                    bot.send_document(chat_id, file, caption=caption)
        return True
    except Exception as e:
        return False

@bot.message_handler(commands=['start'])
def start_command(message):
    text = "🤖 Bot con miniatura personalizada\n\nEnvía un archivo o enlace"
    bot.send_message(message.chat.id, text)

@bot.message_handler(content_types=['document', 'photo', 'video', 'audio'])
def handle_direct_file(message):
    try:
        if message.document:
            file_id = message.document.file_id
            filename = message.document.file_name or "documento"
        elif message.photo:
            file_id = message.photo[-1].file_id
            filename = "foto.jpg"
        elif message.video:
            file_id = message.video.file_id
            filename = "video.mp4"
        elif message.audio:
            file_id = message.audio.file_id
            filename = message.audio.file_name or "audio.mp3"
        else:
            return

        file_info = bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        response = requests.get(file_url, timeout=30)
        
        if response.status_code != 200:
            return
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_file:
            temp_file.write(response.content)
            temp_path = temp_file.name
        
        enviar_archivo_con_thumbnail(message.chat.id, temp_path, filename)
        os.unlink(temp_path)
            
    except Exception as e:
        pass

@bot.message_handler(func=lambda message: True)
def handle_url(message):
    url = message.text.strip()
    if not url.startswith(('http://', 'https://')):
        return
    
    file_path, filename = descargar_archivo_desde_url(url)
    if file_path:
        enviar_archivo_con_thumbnail(message.chat.id, file_path, filename, url)
        os.unlink(file_path)

if __name__ == "__main__":
    bot.infinity_polling()
