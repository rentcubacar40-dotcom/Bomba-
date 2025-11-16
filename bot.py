import telebot
import requests
import tempfile
import os
import io
import time
from urllib.parse import urlparse
from threading import Thread, Lock, Semaphore
from queue import Queue

# ---------------------------
# CONFIGURACIÓN
# ---------------------------
BOT_TOKEN = "8200566220:AAH4Ld6dhXYxtdsph4s7SHyH2ficT0c3SLw"  # <- pon tu token aquí
bot = telebot.TeleBot(BOT_TOKEN)

THUMBNAIL_URL = "https://raw.githubusercontent.com/rentcubacar40-dotcom/telegram-file-bot/main/assets/foto.jpg"

MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB máximo interno
TELEGRAM_MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB máximo Telegram
CHUNK_SIZE = 64 * 1024  # 64 KB por chunk para mayor velocidad
DOWNLOAD_TIMEOUT = 300  # segundos
PROGRESS_UPDATE_INTERVAL = 2.0  # segundos

# ---------------------------
# COLA DE DESCARGAS
# ---------------------------
download_queue = Queue()
queue_lock = Lock()
semaphore = Semaphore(2)  # máximo 2 descargas simultáneas
active_downloads = {}

# ---------------------------
# UTILIDADES
# ---------------------------
def human_size(num: int) -> str:
    for unit in ["B","KB","MB","GB","TB"]:
        if num < 1024: return f"{num:.2f} {unit}"
        num /= 1024
    return f"{num:.2f} PB"

def crear_barra_progreso(porcentaje, ancho=20):
    completado = int(ancho * porcentaje / 100)
    restante = ancho - completado
    return "█" * completado + "░" * restante

def actualizar_progreso(chat_id, message_id, etapa, porcentaje, velocidad="", tiempo_restante="", transferido=""):
    barra = crear_barra_progreso(porcentaje)
    texto = f"🔄 **{etapa}**\n{barra} **{porcentaje:.1f}%**\n"
    if velocidad:
        texto += f"📊 **Velocidad:** {velocidad}\n"
    if tiempo_restante:
        texto += f"⏱️ **Tiempo restante:** {tiempo_restante}\n"
    if transferido:
        texto += f"📁 **Transferido:** {transferido}\n"
    try:
        bot.edit_message_text(texto, chat_id, message_id, parse_mode='Markdown')
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
    try:
        cd = headers.get('content-disposition')
        if cd and 'filename=' in cd:
            filename = cd.split('filename=')[1].strip('"\' ')
            if '.' in filename:
                return filename
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path)
        if '.' in filename:
            return filename
        return f"archivo_{int(time.time())}.bin"
    except:
        return f"archivo_{int(time.time())}.bin"

# ---------------------------
# DESCARGA Y SUBIDA CON PROGRESO
# ---------------------------
def descargar_y_enviar(chat_id, source_url=None, file_id=None, file_name=None):
    temp_path = None
    progress_msg = bot.send_message(chat_id, "🔄 Preparando descarga...", parse_mode='Markdown')
    try:
        # 1️⃣ Preparar URL o Telegram file
        if file_id:  # archivo de Telegram
            file_info = bot.get_file(file_id)
            source_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
            if not file_name:
                file_name = file_info.file_path.split('/')[-1]

        headers = {'User-Agent': 'Mozilla/5.0'}
        head = requests.head(source_url, headers=headers, timeout=10, allow_redirects=True)
        total_size = int(head.headers.get('content-length', 0))
        if total_size > MAX_FILE_SIZE:
            raise Exception(f"Archivo demasiado grande ({human_size(total_size)})")

        file_name = file_name or obtener_nombre_real(source_url, head.headers)

        # 2️⃣ Descargar con progreso
        response = requests.get(source_url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT)
        response.raise_for_status()
        temp_path = tempfile.mktemp(suffix=os.path.splitext(file_name)[1])
        downloaded = 0
        start_time = time.time()
        last_update = 0

        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
            if chunk:
                with semaphore:  # limitar descargas simultáneas
                    with open(temp_path, 'ab') as f:
                        f.write(chunk)
                        downloaded += len(chunk)
                        # Calcular progreso
                        elapsed = time.time() - start_time
                        speed = downloaded / elapsed if elapsed > 0 else 0
                        speed_txt = f"{human_size(speed)}/s"
                        percent = (downloaded / total_size) * 100 if total_size else 0
                        remaining = (total_size - downloaded) / speed if speed > 0 else 0
                        remaining_txt = f"{int(remaining)}s" if remaining < 60 else f"{remaining/60:.1f}m"
                        transferred = f"{human_size(downloaded)}/{human_size(total_size)}" if total_size else human_size(downloaded)
                        now = time.time()
                        if now - last_update > PROGRESS_UPDATE_INTERVAL:
                            last_update = now
                            actualizar_progreso(chat_id, progress_msg.message_id, "📥 DESCARGANDO", percent, speed_txt, remaining_txt, transferred)

        # 3️⃣ Subida con progreso
        uploaded = 0
        start_upload = time.time()
        class ProgressFile(io.BufferedReader):
            def read(self, n=-1):
                nonlocal uploaded
                chunk = super().read(n)
                if chunk:
                    uploaded += len(chunk)
                    elapsed = time.time() - start_upload
                    speed = uploaded / elapsed if elapsed>0 else 0
                    speed_txt = f"{human_size(speed)}/s"
                    percent = (uploaded / downloaded) * 100 if downloaded else 0
                    remaining = (downloaded - uploaded)/speed if speed>0 else 0
                    remaining_txt = f"{int(remaining)}s" if remaining<60 else f"{remaining/60:.1f}m"
                    actualizar_progreso(chat_id, progress_msg.message_id, "📤 SUBIENDO", percent, speed_txt, remaining_txt, f"{human_size(uploaded)}/{human_size(downloaded)}")
                return chunk

        thumb = obtener_miniatura()
        with ProgressFile(open(temp_path,'rb')) as f:
            bot.send_document(chat_id, f, visible_file_name=file_name, caption=f"`{file_name}`", parse_mode='Markdown', thumb=thumb)

        bot.delete_message(chat_id, progress_msg.message_id)
        bot.send_message(chat_id, f"✅ Proceso completado: `{file_name}`", parse_mode='Markdown')

    except Exception as e:
        bot.edit_message_text(f"❌ Error: `{str(e)}`", chat_id, progress_msg.message_id, parse_mode='Markdown')
    finally:
        if temp_path and os.path.exists(temp_path):
            try: os.unlink(temp_path)
            except: pass

# ---------------------------
# HANDLERS
# ---------------------------
@bot.message_handler(commands=['start'])
def start_command(message):
    bot.send_message(message.chat.id, "🤖 **File Processor Pro**\nEnvía un archivo o un enlace para procesarlo.\nUsa /ayuda para más información.", parse_mode='Markdown')

@bot.message_handler(commands=['ayuda'])
def ayuda_command(message):
    bot.send_message(message.chat.id, "📘 **AYUDA**\n• Envía archivos (document, photo, video, audio) o enlaces (http/https).\n• Tamaño máximo: 500MB\n• Comandos: /start /ayuda /estado /queue /cancel", parse_mode='Markdown')

@bot.message_handler(commands=['estado'])
def estado_command(message):
    bot.send_message(message.chat.id, "🟢 Sistema operativo y estable", parse_mode='Markdown')

# Archivos directos
@bot.message_handler(content_types=['document','photo','video','audio'])
def handle_file(message):
    Thread(target=descargar_y_enviar, args=(message.chat.id, None, getattr(message.document,'file_id', None) or getattr(message.photo[-1],'file_id', None), getattr(message.document,'file_name', None))).start()

# Enlaces
@bot.message_handler(func=lambda m: m.text and m.text.startswith(('http://','https://')))
def handle_url(message):
    Thread(target=descargar_y_enviar, args=(message.chat.id, message.text.strip())).start()

# Fallback
@bot.message_handler(func=lambda m: True)
def fallback(message):
    bot.reply_to(message, "Envía un archivo o enlace (http/https). Usa /ayuda para más detalles.", parse_mode='Markdown')

# ---------------------------
# BUCLE PRINCIPAL
# ---------------------------
def main():
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e:
            print(f"Error crítico: {e}. Reiniciando en 5s...")
            time.sleep(5)

if __name__=="__main__":
    main()
