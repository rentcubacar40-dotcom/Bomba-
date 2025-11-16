import telebot
import requests
import tempfile
import os
import io
import time
from urllib.parse import urlparse
from zipfile import ZipFile

# -------------------------
# CONFIGURACIÓN
# -------------------------
BOT_TOKEN = "8200566220:AAH4Ld6dhXYxtdsph4s7SHyH2ficT0c3SLw"  # <- coloca tu token aquí
bot = telebot.TeleBot(BOT_TOKEN)

THUMBNAIL_URL = "https://raw.githubusercontent.com/rentcubacar40-dotcom/telegram-file-bot/main/assets/foto.jpg"

MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
CHUNK_SIZE = 64 * 1024  # 64 KB
DOWNLOAD_TIMEOUT = 300
PROGRESS_INTERVAL = 5  # segundos entre actualizaciones

# -------------------------
# UTILIDADES
# -------------------------
def human_size(num: int) -> str:
    for unit in ["B","KB","MB","GB"]:
        if num < 1024: return f"{num:.2f} {unit}"
        num /= 1024
    return f"{num:.2f} TB"

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

def comprimir_archivo_si_peligroso(file_path):
    """Comprime archivos peligrosos como .apk, .exe, .ipa"""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ['.apk', '.exe', '.ipa', '.bat', '.jar']:
        zip_path = tempfile.mktemp(suffix=".zip")
        with ZipFile(zip_path,'w') as zipf:
            zipf.write(file_path, arcname=os.path.basename(file_path))
        return zip_path, True
    return file_path, False

# -------------------------
# ENVÍO CON PROGRESO REAL
# -------------------------
def send_document_con_progreso(chat_id, file_path, filename, thumb=None):
    file_size = os.path.getsize(file_path)
    start_time = time.time()
    uploaded_bytes = 0

    # Wrapper personalizado usando un stream
    class FileWrapper(io.BufferedReader):
        def read(self, n=-1):
            nonlocal uploaded_bytes
            chunk = super().read(n)
            if chunk:
                uploaded_bytes += len(chunk)
                elapsed = time.time() - start_time
                velocidad = human_size(uploaded_bytes/(elapsed+0.01))+"/s"
                percent = uploaded_bytes/file_size*100
                actualizar_progreso(chat_id, progress_msg.message_id, "📤 SUBIENDO", percent, velocidad, transferido=f"{human_size(uploaded_bytes)}/{human_size(file_size)}")
            return chunk

    with open(file_path,'rb') as f:
        wrapped = FileWrapper(f)
        bot.send_document(chat_id, wrapped, visible_file_name=filename, caption=f"`{filename}`", parse_mode='Markdown', thumb=thumb)

# -------------------------
# DESCARGA Y ENVÍO
# -------------------------
def descargar_y_enviar(chat_id, url=None, file_id=None, filename=None):
    global progress_msg
    temp_path = None
    progress_msg = bot.send_message(chat_id, "🔄 Preparando descarga...", parse_mode='Markdown')
    try:
        if file_id:
            info = bot.get_file(file_id)
            url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{info.file_path}"
            if not filename:
                filename = info.file_path.split('/')[-1]

        headers = {'User-Agent': 'Mozilla/5.0'}
        head = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
        total_size = int(head.headers.get('content-length', 0))
        if total_size > MAX_FILE_SIZE:
            raise Exception(f"Archivo demasiado grande ({human_size(total_size)})")

        filename = filename or obtener_nombre_real(url, head.headers)

        # Descarga con progreso
        response = requests.get(url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT)
        response.raise_for_status()
        temp_path = tempfile.mktemp(suffix=os.path.splitext(filename)[1])
        downloaded = 0
        start_time = time.time()
        last_update = 0

        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    elapsed = time.time() - start_time
                    speed = downloaded/elapsed if elapsed>0 else 0
                    percent = downloaded/total_size*100 if total_size else 0
                    remaining = (total_size-downloaded)/speed if speed>0 else 0
                    now = time.time()
                    if now - last_update > PROGRESS_INTERVAL:
                        last_update = now
                        actualizar_progreso(chat_id, progress_msg.message_id, "📥 DESCARGANDO", percent, f"{human_size(speed)}/s", f"{int(remaining)}s" if remaining<60 else f"{remaining/60:.1f}m", f"{human_size(downloaded)}/{human_size(total_size)}")

        # Comprimir si necesario
        final_path, comprimido = comprimir_archivo_si_peligroso(temp_path)
        if comprimido:
            bot.send_message(chat_id, "⚠️ Archivo peligroso detectado. Se ha comprimido a `.zip` para poder enviarlo.", parse_mode='Markdown')
            filename = os.path.basename(final_path)

        # Enviar con progreso real
        thumb = obtener_miniatura()
        send_document_con_progreso(chat_id, final_path, filename, thumb)

        bot.delete_message(chat_id, progress_msg.message_id)
        bot.send_message(chat_id, f"✅ Proceso completado: `{filename}`", parse_mode='Markdown')

    except Exception as e:
        bot.edit_message_text(f"❌ Error: `{str(e)}`", chat_id, progress_msg.message_id, parse_mode='Markdown')
    finally:
        if temp_path and os.path.exists(temp_path):
            try: os.unlink(temp_path)
            except: pass

# -------------------------
# HANDLERS
# -------------------------
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🤖 **File Processor Pro**\nEnvía un archivo o enlace para procesarlo.\nUsa /ayuda para más información.", parse_mode='Markdown')

@bot.message_handler(commands=['ayuda'])
def ayuda(message):
    bot.send_message(message.chat.id, "📘 **AYUDA**\n• Envía archivos o enlaces (http/https)\n• Tamaño máximo: 500MB\n• Archivos peligrosos (.apk, .exe, .ipa) se enviarán como .zip\n• Soporta documentos, fotos, videos y audio", parse_mode='Markdown')

@bot.message_handler(content_types=['document','photo','video','audio'])
def handle_file(message):
    file_id = None
    filename = None
    if message.document:
        file_id = message.document.file_id
        filename = message.document.file_name
    elif message.photo:
        file_id = message.photo[-1].file_id
        filename = f"image_{int(time.time())}.jpg"
    elif message.video:
        file_id = message.video.file_id
        filename = f"video_{int(time.time())}.mp4"
    elif message.audio:
        file_id = message.audio.file_id
        filename = message.audio.file_name
    descargar_y_enviar(message.chat.id, file_id=file_id, filename=filename)

@bot.message_handler(func=lambda m: m.text and m.text.startswith(('http://','https://')))
def handle_url(message):
    descargar_y_enviar(message.chat.id, url=message.text.strip())

@bot.message_handler(func=lambda m: True)
def fallback(message):
    bot.reply_to(message, "Envía un archivo o enlace válido (http/https). Usa /ayuda para más información.", parse_mode='Markdown')

# -------------------------
# MAIN
# -------------------------
if __name__=="__main__":
    print("🚀 File Processor Pro iniciado correctamente")
    bot.infinity_polling(timeout=60, long_polling_timeout=30)
