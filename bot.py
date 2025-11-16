import asyncio
import logging
import os
import sys
import tempfile
import time
import io
from typing import Optional

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor
from aiogram.utils.exceptions import RetryAfter, NetworkError

# ---------------------------
# CONFIGURACIÓN
# ---------------------------
BOT_TOKEN = "8200566220:AAH4Ld6dhXYxtdsph4s7SHyH2ficT0c3SLw"  # <- pon aquí tu token
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB límite Telegram
INTERNAL_MAX_FILE_SIZE = 500 * 1024 * 1024  # límite interno opcional
DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=600)  # 10 min
CHUNK_SIZE = 64 * 1024
CONCURRENT_DOWNLOADS = 2
PROGRESS_UPDATE_INTERVAL = 2.0  # segundos
THUMBNAIL_URL = "https://raw.githubusercontent.com/rentcubacar40-dotcom/telegram-file-bot/main/assets/foto.jpg"

# ---------------------------
# LOGGER
# ---------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("fileprocessor")

# ---------------------------
# AIORGRAM GLOBALS
# ---------------------------
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
download_semaphore = asyncio.Semaphore(CONCURRENT_DOWNLOADS)
last_activity = time.time()
WATCHDOG_INTERVAL = 60
WATCHDOG_STUCK_SECONDS = 300

# ---------------------------
# UTILIDADES
# ---------------------------
def human_size(num: int) -> str:
    for unit in ["B","KB","MB","GB","TB"]:
        if num < 1024: return f"{num:.2f} {unit}"
        num /= 1024
    return f"{num:.2f} PB"

def panel_text(etapa: str, percent: float, speed: str, remaining: str, transferred: str) -> str:
    barra = "█" * int(percent // 5) + "░" * (20 - int(percent // 5))
    return (
        f"🖥 **FILE PROCESSOR PRO**\n\n"
        f"🔧 **Estado:** {etapa}\n"
        f"📊 **Progreso:** {barra} {percent:.1f}%\n"
        f"📁 **Transferido:** {transferred}\n"
        f"🚀 **Velocidad:** {speed}\n"
        f"⏱ **Restante:** {remaining}\n"
    )

async def fetch_thumbnail_bytes(session: aiohttp.ClientSession) -> Optional[bytes]:
    try:
        async with session.get(THUMBNAIL_URL, timeout=10) as r:
            if r.status == 200: return await r.read()
    except: pass
    return None

# ---------------------------
# WATCHDOG
# ---------------------------
async def watchdog_loop():
    global last_activity
    while True:
        await asyncio.sleep(WATCHDOG_INTERVAL)
        idle = time.time() - last_activity
        if idle > WATCHDOG_STUCK_SECONDS:
            logger.critical(f"Watchdog detectó inactividad ({idle:.0f}s). Reiniciando...")
            try: await bot.close()
            except: pass
            os.execv(sys.executable, [sys.executable] + sys.argv)

# ---------------------------
# DESCARGA ASÍNCRONA
# ---------------------------
async def async_download_with_progress(url: str, chat_id: int, panel_msg_id: int, session: aiohttp.ClientSession):
    global last_activity
    for attempt in range(1,5):
        try:
            async with download_semaphore:
                async with session.head(url, timeout=DOWNLOAD_TIMEOUT, allow_redirects=True) as head:
                    total = int(head.headers.get("content-length") or 0)
                    filename = head.headers.get("content-disposition")
                    if filename and "filename=" in filename: filename = filename.split("filename=")[1].strip('"\' ')
                    else: filename = os.path.basename(url.split("?")[0]) or f"archivo_{int(time.time())}.bin"

                if total and total > MAX_FILE_SIZE:
                    raise Exception(f"Archivo demasiado grande ({human_size(total)}). Límite: {human_size(MAX_FILE_SIZE)}")

                async with session.get(url, timeout=DOWNLOAD_TIMEOUT) as resp:
                    resp.raise_for_status()
                    fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(filename)[1])
                    os.close(fd)
                    downloaded = 0
                    start = time.time()
                    last_update = 0
                    with open(tmp_path,"wb") as f:
                        async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                            if not chunk: continue
                            f.write(chunk)
                            downloaded += len(chunk)
                            last_activity = time.time()
                            if downloaded > INTERNAL_MAX_FILE_SIZE and INTERNAL_MAX_FILE_SIZE < MAX_FILE_SIZE:
                                logger.warning("Se excedió INTERNAL_MAX_FILE_SIZE")

                            elapsed = time.time() - start
                            speed = downloaded/elapsed if elapsed>0 else 0
                            speed_txt = human_size(speed) + "/s"
                            percent = (downloaded/total*100) if total else 0.0
                            remaining = ((total - downloaded)/speed) if (speed>0 and total) else None
                            remaining_txt = f"{remaining:.0f}s" if remaining and remaining<60 else (f"{remaining/60:.1f}m" if remaining else "Calculando...")
                            transferred_txt = f"{human_size(downloaded)}" + (f"/{human_size(total)}" if total else "")
                            now=time.time()
                            if now-last_update>PROGRESS_UPDATE_INTERVAL or percent>=100:
                                last_update=now
                                try:
                                    await bot.edit_message_text(chat_id=chat_id,message_id=panel_msg_id,text=panel_text("DESCARGANDO",percent,speed_txt,remaining_txt,transferred_txt),parse_mode="Markdown")
                                except: pass
                    return tmp_path, filename
        except Exception as e:
            if attempt<4:
                await asyncio.sleep(2**attempt)
                continue
            raise e

# ---------------------------
# ENVÍO DE ARCHIVO
# ---------------------------
async def send_document_with_thumb(chat_id:int,file_path:str,filename:str,thumb_bytes:Optional[bytes]=None):
    attempts=4
    backoff=2
    for i in range(attempts):
        try:
            with open(file_path,"rb") as f:
                await bot.send_document(chat_id, types.InputFile(f, filename=filename), caption=f"`{filename}`", parse_mode="Markdown")
                return True
        except RetryAfter as e:
            await asyncio.sleep(e.timeout+1)
        except Exception:
            await asyncio.sleep(backoff**i)
            continue
    raise Exception("No se pudo enviar el archivo")

# ---------------------------
# HANDLERS
# ---------------------------
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    global last_activity
    last_activity=time.time()
    await message.reply("🤖 **File Processor Pro (Aiogram)**\nEnvía un archivo o enlace y lo procesaré.\nUsa /ayuda.",parse_mode="Markdown")

@dp.message_handler(commands=["ayuda"])
async def cmd_ayuda(message: types.Message):
    global last_activity
    last_activity=time.time()
    await message.reply("📘 **AYUDA**\n• Envía archivos (document, photo, video, audio) o enlaces (http/https).\n• Límite Telegram: 2GB\n• Interno: 500MB\nComandos: /start /ayuda /estado",parse_mode="Markdown")

@dp.message_handler(commands=["estado"])
async def cmd_estado(message: types.Message):
    global last_activity
    last_activity=time.time()
    await message.reply("🟢 Sistema operativo y estable",parse_mode="Markdown")

# ---------------------------
# ARCHIVOS DIRECTOS
# ---------------------------
@dp.message_handler(content_types=[types.ContentType.DOCUMENT, types.ContentType.PHOTO, types.ContentType.VIDEO, types.ContentType.AUDIO])
async def handle_file(message: types.Message):
    global last_activity
    last_activity=time.time()
    chat_id = message.chat.id

    # Obtener información del archivo
    if message.document:
        file_id = message.document.file_id
        filename = message.document.file_name or f"file_{int(time.time())}.bin"
        file_size = message.document.file_size or 0
    elif message.photo:
        file_id = message.photo[-1].file_id
        filename = f"photo_{int(time.time())}.jpg"
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

    if file_size>MAX_FILE_SIZE:
        await message.reply(f"❌ Archivo demasiado grande: {human_size(file_size)}",parse_mode="Markdown")
        return

    panel = await message.reply("🔄 Preparando descarga desde Telegram...",parse_mode="Markdown")
    try:
        file_info = await bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        async with aiohttp.ClientSession(timeout=DOWNLOAD_TIMEOUT) as session:
            tmp_path, fname = await async_download_with_progress(file_url, chat_id, panel.message_id, session)
            thumb_bytes = await fetch_thumbnail_bytes(session)
            await send_document_with_thumb(chat_id, tmp_path, filename, thumb_bytes)
            await bot.delete_message(chat_id, panel.message_id)
            await message.reply(f"✅ Proceso completado: `{filename}`",parse_mode="Markdown")
    finally:
        try: os.unlink(tmp_path)
        except: pass
        last_activity=time.time()

# ---------------------------
# MENSAJES CON URL
# ---------------------------
@dp.message_handler(lambda msg: msg.text and msg.text.lower().startswith(("http://","https://")))
async def handle_url(message: types.Message):
    global last_activity
    last_activity=time.time()
    url = message.text.strip()
    chat_id = message.chat.id
    panel = await message.reply("🔎 Analizando enlace...",parse_mode="Markdown")
    try:
        async with aiohttp.ClientSession(timeout=DOWNLOAD_TIMEOUT) as session:
            tmp_path, filename = await async_download_with_progress(url, chat_id, panel.message_id, session)
            thumb_bytes = await fetch_thumbnail_bytes(session)
            await send_document_with_thumb(chat_id, tmp_path, filename, thumb_bytes)
            await bot.delete_message(chat_id, panel.message_id)
            await message.reply(f"✅ Descarga completada: `{filename}`",parse_mode="Markdown")
    finally:
        try: os.unlink(tmp_path)
        except: pass
        last_activity=time.time()

# ---------------------------
# MENSAJES FALLBACK
# ---------------------------
@dp.message_handler()
async def fallback(message: types.Message):
    await message.reply("Envía un archivo o enlace (http/https). Usa /ayuda para más detalles.",parse_mode="Markdown")

# ---------------------------
# STARTUP / SHUTDOWN
# ---------------------------
async def on_startup(dp: Dispatcher):
    logger.info("Iniciando File Processor Pro (Aiogram)")
    asyncio.create_task(watchdog_loop())

async def on_shutdown(dp: Dispatcher):
    logger.info("Cerrando bot...")
    await bot.close()

# ---------------------------
# EJECUCIÓN RESILIENTE
# ---------------------------
def main():
    while True:
        try:
            executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)
        except Exception as e:
            logger.exception(f"Loop falló: {e} - reiniciando en 5s")
            time.sleep(5)

if __name__=="__main__":
    main()
