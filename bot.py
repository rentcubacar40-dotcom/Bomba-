import telebot
import requests
import tempfile
import os
import io
import time
from urllib.parse import urlparse
from datetime import datetime

BOT_TOKEN = "8200566220:AAH4Ld6dhXYxtdsph4s7SHyH2ficT0c3SLw"
bot = telebot.TeleBot(BOT_TOKEN)

THUMBNAIL_URL = "https://raw.githubusercontent.com/rentcubacar40-dotcom/telegram-file-bot/main/assets/foto.jpg"

def crear_barra_progreso(porcentaje, ancho=20):
    """Crear barra de progreso visual"""
    completado = int(ancho * porcentaje / 100)
    restante = ancho - completado
    return "█" * completado + "░" * restante

def actualizar_progreso(chat_id, message_id, etapa, porcentaje, velocidad="", tiempo_restante=""):
    """Actualizar mensaje de progreso"""
    barra = crear_barra_progreso(porcentaje)
    
    texto = f"""
🔄 **{etapa}**
{barra} **{porcentaje}%**

"""
    
    if velocidad:
        texto += f"📊 **Velocidad:** {velocidad}\n"
    if tiempo_restante:
        texto += f"⏱️ **Tiempo restante:** {tiempo_restante}\n"
    
    try:
        bot.edit_message_text(
            texto,
            chat_id,
            message_id,
            parse_mode='Markdown'
        )
    except:
        pass

def obtener_miniatura():
    try:
        response = requests.get(THUMBNAIL_URL, timeout=10)
        if response.status_code == 200:
            return io.BytesIO(response.content)
        return None
    except:
        return None

def obtener_nombre_real(url, headers):
    if 'content-disposition' in headers:
        cd = headers['content-disposition']
        if 'filename=' in cd:
            filename = cd.split('filename=')[1].strip('"\'')
            if '.' in filename:
                return filename
    
    parsed = urlparse(url)
    path = parsed.path
    if '/' in path:
        filename = path.split('/')[-1]
        if '.' in filename:
            return filename
    
    return f"archivo_{int(time.time())}.bin"

def descargar_con_progreso(url, chat_id, progress_msg):
    """Descargar archivo mostrando progreso en tiempo real"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        # Obtener tamaño total
        head_response = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
        filename = obtener_nombre_real(url, head_response.headers)
        total_size = int(head_response.headers.get('content-length', 0))
        
        # Iniciar descarga
        response = requests.get(url, headers=headers, timeout=30, stream=True)
        response.raise_for_status()
        
        # Preparar archivo temporal
        temp_path = tempfile.mktemp(suffix=os.path.splitext(filename)[1])
        downloaded = 0
        start_time = time.time()
        
        with open(temp_path, 'wb') as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
                    downloaded += len(chunk)
                    
                    # Calcular métricas
                    elapsed_time = time.time() - start_time
                    if elapsed_time > 0:
                        speed = downloaded / elapsed_time
                        speed_text = f"{speed/1024/1024:.1f} MB/s"
                        
                        if speed > 0 and total_size > 0:
                            remaining_time = (total_size - downloaded) / speed
                            if remaining_time < 60:
                                time_text = f"{remaining_time:.0f}s"
                            else:
                                time_text = f"{remaining_time/60:.1f}m"
                        else:
                            time_text = "Calculando..."
                    else:
                        speed_text = "Calculando..."
                        time_text = "Calculando..."
                    
                    # Actualizar progreso
                    if total_size > 0:
                        percent = min(100, (downloaded / total_size) * 100)
                        actualizar_progreso(
                            chat_id, 
                            progress_msg.message_id,
                            "📥 DESCARGANDO ARCHIVO",
                            percent,
                            speed_text,
                            time_text
                        )
        
        return temp_path, filename
        
    except Exception as e:
        print(f"Error descargando: {e}")
        return None, None

def enviar_como_documento_con_thumbnail(chat_id, file_path, filename, url_original=None):
    try:
        with open(file_path, 'rb') as file:
            caption = f"`{filename}`"
            if url_original:
                caption += f"\n\n🔗 *Enlace procesado*"
            
            thumbnail = obtener_miniatura()
            
            if thumbnail:
                bot.send_document(
                    chat_id,
                    file,
                    caption=caption,
                    visible_file_name=filename,
                    thumbnail=thumbnail,
                    parse_mode='Markdown'
                )
            else:
                bot.send_document(
                    chat_id,
                    file,
                    caption=caption,
                    visible_file_name=filename,
                    parse_mode='Markdown'
                )
        
        return True
        
    except Exception as e:
        print(f"Error enviando: {e}")
        return False

@bot.message_handler(commands=['start'])
def start_command(message):
    text = """
🤖 **File Processor Pro**

*Sistema profesional de procesamiento de archivos*
- Progreso en tiempo real
- Métricas de rendimiento  
- Thumbnails personalizados
- Nomenclatura precisa

*Envía un archivo o enlace directo*
    """
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(content_types=['document', 'photo', 'video', 'audio'])
def handle_direct_file(message):
    try:
        if message.document:
            file_id = message.document.file_id
            filename = message.document.file_name or f"document_{int(time.time())}.bin"
        elif message.photo:
            file_id = message.photo[-1].file_id
            filename = f"image_{int(time.time())}.jpg"
        elif message.video:
            file_id = message.video.file_id
            filename = f"video_{int(time.time())}.mp4"
        elif message.audio:
            file_id = message.audio.file_id
            filename = message.audio.file_name or f"audio_{int(time.time())}.mp3"
        else:
            return

        # Progreso: Descargando
        progress_msg = bot.reply_to(message, "🔄 **PREPARANDO PROCESO**\n\nInicializando sistema...", parse_mode='Markdown')
        
        actualizar_progreso(
            message.chat.id,
            progress_msg.message_id,
            "📥 DESCARGANDO DE TELEGRAM",
            0,
            "Iniciando...",
            "Calculando..."
        )

        # Descargar archivo
        file_info = bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        
        file_size = 0
        if message.document:
            file_size = message.document.file_size or 0
        downloaded = 0
        start_time = time.time()
        
        response = requests.get(file_url, timeout=30, stream=True)
        if response.status_code != 200:
            bot.edit_message_text("❌ **ERROR EN DESCARGA**", message.chat.id, progress_msg.message_id, parse_mode='Markdown')
            return
        
        temp_path = tempfile.mktemp(suffix=os.path.splitext(filename)[1])
        
        with open(temp_path, 'wb') as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
                    downloaded += len(chunk)
                    
                    # Calcular progreso
                    elapsed = time.time() - start_time
                    if elapsed > 0 and file_size > 0:
                        speed = downloaded / elapsed
                        percent = min(100, (downloaded / file_size) * 100)
                        
                        speed_text = f"{speed/1024/1024:.1f} MB/s" if speed > 1024*1024 else f"{speed/1024:.1f} KB/s"
                        
                        remaining = (file_size - downloaded) / speed if speed > 0 else 0
                        time_text = f"{remaining:.1f}s" if remaining < 60 else f"{remaining/60:.1f}m"
                        
                        actualizar_progreso(
                            message.chat.id,
                            progress_msg.message_id,
                            "📥 DESCARGANDO ARCHIVO",
                            percent,
                            speed_text,
                            time_text
                        )

        # Progreso: Procesando
        actualizar_progreso(
            message.chat.id,
            progress_msg.message_id,
            "🎨 APLICANDO THUMBNAIL",
            100,
            "Completado",
            "0s"
        )
        
        time.sleep(1)  # Pequeña pausa para ver el 100%

        # Enviar archivo
        success = enviar_como_documento_con_thumbnail(message.chat.id, temp_path, filename)

        # Limpiar
        bot.delete_message(message.chat.id, progress_msg.message_id)
        os.unlink(temp_path)
        
        if success:
            bot.reply_to(message, f"✅ **PROCESO COMPLETADO**\n\n`{filename}`", parse_mode='Markdown')
            
    except Exception as e:
        bot.reply_to(message, f"❌ **ERROR DEL SISTEMA**\n\n`{str(e)}`", parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def handle_url(message):
    url = message.text.strip()
    
    if not url.startswith(('http://', 'https://')):
        bot.reply_to_message(message, "❌ **URL NO VÁLIDA**\n\nFormato requerido: `http://` o `https://`", parse_mode='Markdown')
        return
    
    try:
        # Progreso: Verificando
        progress_msg = bot.reply_to(message, "🔄 **INICIANDO ANÁLISIS**\n\nVerificando enlace...", parse_mode='Markdown')
        
        # Descargar con progreso
        file_path, filename = descargar_con_progreso(url, message.chat.id, progress_msg)
        
        if not file_path:
            bot.edit_message_text("❌ **ERROR EN DESCARGA**", message.chat.id, progress_msg.message_id, parse_mode='Markdown')
            return

        # Progreso: Finalizando
        actualizar_progreso(
            message.chat.id,
            progress_msg.message_id,
            "✅ PROCESO COMPLETADO",
            100,
            "Finalizado",
            "0s"
        )
        
        time.sleep(1)
        
        # Enviar archivo
        success = enviar_como_documento_con_thumbnail(message.chat.id, file_path, filename, url)

        # Limpiar
        bot.delete_message(message.chat.id, progress_msg.message_id)
        os.unlink(file_path)
        
        if success:
            bot.reply_to(message, f"✅ **DESCARGA COMPLETADA**\n\n`{filename}`", parse_mode='Markdown')
            
    except Exception as e:
        bot.edit_message_text(f"❌ **ERROR DEL SISTEMA**\n\n`{str(e)}`", message.chat.id, progress_msg.message_id, parse_mode='Markdown')

if __name__ == "__main__":
    print("🚀 File Processor Pro - Sistema iniciado")
    bot.infinity_polling()
