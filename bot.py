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

# CONFIGURACIONES DE SEGURIDAD
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB máximo
DOWNLOAD_TIMEOUT = 300  # 5 minutos máximo por descarga
CHUNK_SIZE = 8192

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
    except Exception as e:
        print(f"Error editando mensaje: {e}")

def obtener_miniatura():
    try:
        response = requests.get(THUMBNAIL_URL, timeout=10)
        if response.status_code == 200:
            return io.BytesIO(response.content)
        return None
    except Exception as e:
        print(f"Error obteniendo miniatura: {e}")
        return None

def obtener_nombre_real(url, headers):
    try:
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
            if '.' in filename and len(filename) > 0:
                return filename
        
        return f"archivo_{int(time.time())}.bin"
    except Exception as e:
        print(f"Error obteniendo nombre: {e}")
        return f"archivo_{int(time.time())}.bin"

def descargar_con_progreso(url, chat_id, progress_msg):
    """Descargar archivo mostrando progreso en tiempo real"""
    temp_path = None
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        # Obtener tamaño total con timeout
        head_response = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
        
        # Verificar tamaño del archivo
        total_size = int(head_response.headers.get('content-length', 0))
        if total_size > MAX_FILE_SIZE:
            raise Exception(f"Archivo demasiado grande ({total_size/1024/1024:.1f}MB). Máximo permitido: {MAX_FILE_SIZE/1024/1024}MB")
        
        filename = obtener_nombre_real(url, head_response.headers)
        
        # Iniciar descarga con timeout más largo
        response = requests.get(url, headers=headers, timeout=DOWNLOAD_TIMEOUT, stream=True)
        response.raise_for_status()
        
        # Preparar archivo temporal
        temp_path = tempfile.mktemp(suffix=os.path.splitext(filename)[1])
        downloaded = 0
        start_time = time.time()
        
        with open(temp_path, 'wb') as temp_file:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    temp_file.write(chunk)
                    downloaded += len(chunk)
                    
                    # Verificar tamaño durante descarga
                    if downloaded > MAX_FILE_SIZE:
                        raise Exception("Archivo excede el tamaño máximo durante la descarga")
                    
                    # Calcular métricas
                    elapsed_time = time.time() - start_time
                    if elapsed_time > 0:
                        speed = downloaded / elapsed_time
                        speed_text = f"{speed/1024/1024:.1f} MB/s" if speed > 1024*1024 else f"{speed/1024:.1f} KB/s"
                        
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
                    
                    # Actualizar progreso cada 5% o 5 segundos
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
        
    except requests.exceptions.Timeout:
        raise Exception("Timeout: La descarga tomó demasiado tiempo")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Error de conexión: {str(e)}")
    except Exception as e:
        # Limpiar archivo temporal en caso de error
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass
        raise e

def enviar_como_documento_con_thumbnail(chat_id, file_path, filename, url_original=None):
    try:
        # Verificar que el archivo existe y tiene tamaño
        if not os.path.exists(file_path):
            raise Exception("Archivo no encontrado después de la descarga")
        
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            raise Exception("Archivo vacío")
        
        with open(file_path, 'rb') as file:
            caption = f"`{filename}`"
            if url_original:
                caption += f"\n\n🔗 *Enlace procesado*"
            
            thumbnail = obtener_miniatura()
            
            # Enviar con manejo de errores específico
            if thumbnail:
                sent_msg = bot.send_document(
                    chat_id,
                    file,
                    caption=caption,
                    visible_file_name=filename,
                    thumbnail=thumbnail,
                    parse_mode='Markdown',
                    timeout=DOWNLOAD_TIMEOUT
                )
            else:
                sent_msg = bot.send_document(
                    chat_id,
                    file,
                    caption=caption,
                    visible_file_name=filename,
                    parse_mode='Markdown',
                    timeout=DOWNLOAD_TIMEOUT
                )
        
        return True
        
    except telebot.apihelper.ApiTelegramException as e:
        if "file is too big" in str(e):
            raise Exception("El archivo es demasiado grande para enviar por Telegram (máximo 50MB)")
        else:
            raise Exception(f"Error de Telegram API: {str(e)}")
    except Exception as e:
        raise Exception(f"Error enviando archivo: {str(e)}")

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

📝 **Límites:**
• Archivos hasta 500MB
• Tiempo máximo 5 minutos
    """
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(content_types=['document', 'photo', 'video', 'audio'])
def handle_direct_file(message):
    temp_path = None
    progress_msg = None
    
    try:
        # Obtener información del archivo
        if message.document:
            file_id = message.document.file_id
            filename = message.document.file_name or f"document_{int(time.time())}.bin"
            file_size = message.document.file_size or 0
        elif message.photo:
            file_id = message.photo[-1].file_id
            filename = f"image_{int(time.time())}.jpg"
            file_size = 0
        elif message.video:
            file_id = message.video.file_id
            filename = f"video_{int(time.time())}.mp4"
            file_size = message.video.file_size or 0
        elif message.audio:
            file_id = message.audio.file_id
            filename = message.audio.file_name or f"audio_{int(time.time())}.mp3"
            file_size = message.audio.file_size or 0
        else:
            return

        # Verificar tamaño del archivo
        if file_size > MAX_FILE_SIZE:
            bot.reply_to(message, f"❌ **ARCHIVO DEMASIADO GRANDE**\n\nTamaño: {file_size/1024/1024:.1f}MB\nMáximo permitido: {MAX_FILE_SIZE/1024/1024}MB", parse_mode='Markdown')
            return

        # Mensaje de progreso
        progress_msg = bot.reply_to(message, "🔄 **PREPARANDO PROCESO**\n\nInicializando sistema...", parse_mode='Markdown')
        
        actualizar_progreso(
            message.chat.id,
            progress_msg.message_id,
            "📥 DESCARGANDO DE TELEGRAM",
            0,
            "Iniciando...",
            "Calculando..."
        )

        # Descargar archivo de Telegram
        file_info = bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        
        downloaded = 0
        start_time = time.time()
        
        response = requests.get(file_url, timeout=DOWNLOAD_TIMEOUT, stream=True)
        if response.status_code != 200:
            raise Exception(f"Error descargando archivo: HTTP {response.status_code}")
        
        temp_path = tempfile.mktemp(suffix=os.path.splitext(filename)[1])
        
        with open(temp_path, 'wb') as temp_file:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    temp_file.write(chunk)
                    downloaded += len(chunk)
                    
                    # Verificar tamaño durante descarga
                    if downloaded > MAX_FILE_SIZE:
                        raise Exception("Archivo excede el tamaño máximo durante la descarga")
                    
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

        # Verificar que se descargó completo
        if file_size > 0 and downloaded < file_size:
            raise Exception("Descarga incompleta")

        # Procesando
        actualizar_progreso(
            message.chat.id,
            progress_msg.message_id,
            "🎨 APLICANDO THUMBNAIL",
            100,
            "Completado",
            "0s"
        )
        
        time.sleep(1)

        # Enviar archivo
        success = enviar_como_documento_con_thumbnail(message.chat.id, temp_path, filename)

        # Limpiar
        if progress_msg:
            bot.delete_message(message.chat.id, progress_msg.message_id)
        
        if success:
            bot.reply_to(message, f"✅ **PROCESO COMPLETADO**\n\n`{filename}`", parse_mode='Markdown')
            
    except Exception as e:
        error_msg = f"❌ **ERROR DEL SISTEMA**\n\n`{str(e)}`"
        if progress_msg:
            try:
                bot.edit_message_text(error_msg, message.chat.id, progress_msg.message_id, parse_mode='Markdown')
            except:
                bot.reply_to(message, error_msg, parse_mode='Markdown')
        else:
            bot.reply_to(message, error_msg, parse_mode='Markdown')
    
    finally:
        # Limpiar archivo temporal siempre
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception as e:
                print(f"Error eliminando archivo temporal: {e}")

@bot.message_handler(func=lambda message: True)
def handle_url(message):
    url = message.text.strip()
    progress_msg = None
    temp_path = None
    
    if not url.startswith(('http://', 'https://')):
        bot.reply_to(message, "❌ **URL NO VÁLIDA**\n\nFormato requerido: `http://` o `https://`", parse_mode='Markdown')
        return
    
    try:
        # Mensaje de progreso
        progress_msg = bot.reply_to(message, "🔄 **INICIANDO ANÁLISIS**\n\nVerificando enlace...", parse_mode='Markdown')
        
        # Descargar con progreso
        file_path, filename = descargar_con_progreso(url, message.chat.id, progress_msg)
        temp_path = file_path
        
        if not file_path:
            raise Exception("No se pudo descargar el archivo")

        # Procesando
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
        if progress_msg:
            bot.delete_message(message.chat.id, progress_msg.message_id)
        
        if success:
            bot.reply_to(message, f"✅ **DESCARGA COMPLETADA**\n\n`{filename}`", parse_mode='Markdown')
            
    except Exception as e:
        error_msg = f"❌ **ERROR DEL SISTEMA**\n\n`{str(e)}`"
        if progress_msg:
            try:
                bot.edit_message_text(error_msg, message.chat.id, progress_msg.message_id, parse_mode='Markdown')
            except:
                bot.reply_to(message, error_msg, parse_mode='Markdown')
        else:
            bot.reply_to(message, error_msg, parse_mode='Markdown')
    
    finally:
        # Limpiar archivo temporal siempre
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception as e:
                print(f"Error eliminando archivo temporal: {e}")

if __name__ == "__main__":
    print("🚀 File Processor Pro - Sistema iniciado con mejoras de estabilidad")
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=30)
    except Exception as e:
        print(f"Error crítico: {e}")
        time.sleep(10)
        # Reiniciar automáticamente
        os.execv(__file__, sys.argv)
