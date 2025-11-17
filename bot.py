import telebot
import requests
import tempfile
import os
import io
import time
import zipfile
from urllib.parse import urlparse
from datetime import datetime
from PIL import Image
from telebot.types import InputFile

BOT_TOKEN = "TU_TOKEN_AQUI"  # Coloca tu token real aquí
bot = telebot.TeleBot(BOT_TOKEN)

THUMBNAIL_URL = "https://raw.githubusercontent.com/rentcubacar40-dotcom/Bomba-/refs/heads/main/assets/foto.jpg"

MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB máximo
DOWNLOAD_TIMEOUT = 300  # 5 minutos máximo
CHUNK_SIZE = 8192

# -------------------------
# FUNCIONES AUXILIARES
# -------------------------

def human_size(bytes_size):
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024**2:
        return f"{bytes_size/1024:.1f} KB"
    elif bytes_size < 1024**3:
        return f"{bytes_size/1024/1024:.1f} MB"
    else:
        return f"{bytes_size/1024/1024/1024:.1f} GB"

def crear_barra_progreso(porcentaje, ancho=20):
    completado = int(ancho * porcentaje / 100)
    restante = ancho - completado
    return "█" * completado + "░" * restante

def actualizar_progreso(chat_id, message_id, etapa, porcentaje, velocidad="", transferido=""):
    barra = crear_barra_progreso(porcentaje)
    texto = f"🔄 **{etapa}**\n{barra} **{porcentaje:.1f}%**"
    if velocidad:
        texto += f"\n📊 **Velocidad:** {velocidad}"
    if transferido:
        texto += f"\n💾 **Transferido:** {transferido}"
    try:
        bot.edit_message_text(texto, chat_id, message_id, parse_mode='Markdown')
    except Exception:
        pass

# -------------------------
# MINIATURA FUNCIONAL (ARREGLADO)
# -------------------------

def obtener_miniatura():
    """Descarga la miniatura RAW, la procesa y la convierte a InputFile."""
    try:
        resp = requests.get(THUMBNAIL_URL, timeout=10)
        if resp.status_code == 200:
            img = Image.open(io.BytesIO(resp.content))
            img.thumbnail((320, 320))
            buff = io.BytesIO()
            img.save(buff, format="JPEG")
            buff.seek(0)
            return InputFile(buff, filename="thumbnail.jpg")
    except Exception as e:
        print("Error miniatura:", e)
    return None

# -------------------------
# DETECTAR ARCHIVOS PELIGROSOS
# -------------------------

def comprimir_archivo_si_peligroso(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    peligrosas = ['.apk', '.ipa', '.exe', '.bat', '.jar']

    if ext in peligrosas:
        zip_path = tempfile.mktemp(suffix=".zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(file_path, arcname=os.path.basename(file_path))
        return zip_path, True

    return file_path, False

# -------------------------
# NOMBRE REAL DEL ARCHIVO DESDE HEADERS
# -------------------------

def obtener_nombre_real(url, headers):
    try:
        if 'content-disposition' in headers:
            cd = headers['content-disposition']
            if 'filename=' in cd:
                filename = cd.split('filename=')[1].strip('"\'')
                if "." in filename:
                    return filename

        parsed = urlparse(url)
        base = parsed.path.split("/")[-1]
        if "." in base:
            return base

        return f"archivo_{int(time.time())}.bin"

    except:
        return f"archivo_{int(time.time())}.bin"

# -------------------------
# DESCARGA CON PROGRESO
# -------------------------

def descargar_con_progreso(url, chat_id, progress_msg):
    temp_path = None
    try:
        headers = {"User-Agent": "Mozilla/5.0"}

        head = requests.head(url, headers=headers, allow_redirects=True, timeout=10)
        total = int(head.headers.get("content-length", 0))

        if total > MAX_FILE_SIZE:
            raise Exception(f"Archivo demasiado grande ({human_size(total)})")

        filename = obtener_nombre_real(url, head.headers)

        resp = requests.get(url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT)
        resp.raise_for_status()

        temp_path = tempfile.mktemp(suffix=os.path.splitext(filename)[1])
        downloaded = 0
        start = time.time()

        with open(temp_path, "wb") as f:
            for chunk in resp.iter_content(CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        elapsed = time.time() - start
                        speed = downloaded / elapsed
                        percent = downloaded / total * 100
                        actualizar_progreso(
                            chat_id,
                            progress_msg.message_id,
                            "📥 DESCARGANDO ARCHIVO",
                            percent,
                            f"{human_size(speed)}/s",
                            f"{human_size(downloaded)}/{human_size(total)}"
                        )

        return temp_path, filename

    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        raise e

# -------------------------
# SUBIDA CON PROGRESO
# -------------------------

def send_document_con_progreso(chat_id, file_path, filename):
    file_size = os.path.getsize(file_path)
    start = time.time()
    uploaded = 0

    thumb = obtener_miniatura()

    class Wrapper(io.BufferedReader):
        def read(self, n=-1):
            nonlocal uploaded
            chunk = super().read(n)
            if chunk:
                uploaded += len(chunk)
                percent = uploaded / file_size * 100
                elapsed = time.time() - start
                velocidad = human_size(uploaded/(elapsed+0.01)) + "/s"
                actualizar_progreso(
                    chat_id,
                    progress_msg.message_id,
                    "📤 SUBIENDO",
                    percent,
                    velocidad,
                    f"{human_size(uploaded)}/{human_size(file_size)}"
                )
            return chunk

    final_path, comprimido = comprimir_archivo_si_peligroso(file_path)
    if comprimido:
        filename = os.path.basename(final_path)
        bot.send_message(chat_id, "⚠️ Archivo peligroso detectado. Se comprimió a .zip", parse_mode='Markdown')

    with open(final_path, "rb") as original:
        wrapped = Wrapper(original)
        bot.send_document(
            chat_id,
            wrapped,
            visible_file_name=filename,
            caption=f"`{filename}`",
            parse_mode="Markdown",
            thumb=thumb
        )

# -------------------------
# COMANDOS /start y /help
# -------------------------

@bot.message_handler(commands=["start", "help"])
def start_message(message):
    bot.send_message(
        message.chat.id,
        """
🤖 **File Processor Pro**

Envíame:
• Archivos
• Fotos
• Audios
• Videos
• Enlaces directos

Funciones:
✔ Progreso de descarga
✔ Progreso de subida
✔ Miniaturas personalizadas
✔ Apps peligrosas se comprimen a ZIP
✔ Mantiene extensión original de enlaces

⚠️ Tamaños máximos:
• Archivos enviados directo: máx 50MB (por Telegram)
• Enlaces externos: hasta 500MB
        """,
        parse_mode="Markdown"
    )

# -------------------------
# ARCHIVOS ENVIADOS DESDE TELEGRAM
# -------------------------

@bot.message_handler(content_types=["document", "photo", "video", "audio"])
def handle_files(message):
    global progress_msg
    temp_path = None
    try:
        if message.document:
            file_id = message.document.file_id
            filename = message.document.file_name
            file_size = message.document.file_size
        elif message.photo:
            file_id = message.photo[-1].file_id
            filename = f"foto_{int(time.time())}.jpg"
            file_size = 0
        elif message.video:
            file_id = message.video.file_id
            filename = f"video_{int(time.time())}.mp4"
            file_size = message.video.file_size
        elif message.audio:
            file_id = message.audio.file_id
            filename = message.audio.file_name
            file_size = message.audio.file_size

        progress_msg = bot.reply_to(message, "🔄 Preparando...", parse_mode="Markdown")

        file_info = bot.get_file(file_id)
        url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"

        temp_path = tempfile.mktemp(suffix=os.path.splitext(filename)[1])
        downloaded = 0
        start = time.time()

        resp = requests.get(url, stream=True)
        with open(temp_path, "wb") as f:
            for chunk in resp.iter_content(CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if file_size > 0:
                        elapsed = time.time() - start
                        velocidad = human_size(downloaded/(elapsed+0.01)) + "/s"
                        percent = downloaded / file_size * 100
                        actualizar_progreso(
                            message.chat.id,
                            progress_msg.message_id,
                            "📥 DESCARGANDO DE TELEGRAM",
                            percent,
                            velocidad,
                            f"{human_size(downloaded)}/{human_size(file_size)}"
                        )

        send_document_con_progreso(message.chat.id, temp_path, filename)
        bot.delete_message(message.chat.id, progress_msg.message_id)
        bot.reply_to(message, f"✅ Listo: `{filename}`", parse_mode="Markdown")

    except Exception as e:
        bot.edit_message_text(f"❌ Error: `{str(e)}`", message.chat.id, progress_msg.message_id, parse_mode="Markdown")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

# -------------------------
# ENLACES
# -------------------------

@bot.message_handler(func=lambda m: True)
def handle_url(message):
    global progress_msg
    url = message.text.strip()

    if not url.startswith(("http://", "https://")):
        bot.reply_to(message, "❌ URL no válida", parse_mode="Markdown")
        return

    temp_path = None
    try:
        progress_msg = bot.reply_to(message, "🔎 Analizando enlace...", parse_mode="Markdown")
        temp_path, filename = descargar_con_progreso(url, message.chat.id, progress_msg)
        send_document_con_progreso(message.chat.id, temp_path, filename)
        bot.delete_message(message.chat.id, progress_msg.message_id)
        bot.reply_to(message, f"✅ Listo: `{filename}`", parse_mode='Markdown')

    except Exception as e:
        bot.edit_message_text(f"❌ Error: `{str(e)}`", message.chat.id, progress_msg.message_id, parse_mode="Markdown")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

# -------------------------
# MAIN
# -------------------------

if __name__ == "__main__":
    print("🚀 Bot iniciado")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e:
            print("Error crítico:", e)
            time.sleep(10)
