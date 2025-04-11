import time
import subprocess
import threading
from config.settings import CONFIG_CHECK_INTERVAL
from display.screen import show_default_image
from network.client import register_device, get_srt_url, log

class StreamManager:
    def __init__(self):
        self.ffmpeg_process = None
        self.last_config_check = time.time()
        self.last_srt_url = None

    def stop_ffmpeg(self):
        if self.ffmpeg_process:
            log("FFMPEG", "info", "Deteniendo FFmpeg")
            self.ffmpeg_process.terminate()
            self.ffmpeg_process.wait()
            self.ffmpeg_process = None

    def stream_video(self):
        current_time = time.time()
        
        if current_time - self.last_config_check > CONFIG_CHECK_INTERVAL:
            log("STREAM", "info", f"Verificando configuración después de {CONFIG_CHECK_INTERVAL} segundos")
            srt_url = get_srt_url()
            self.last_config_check = current_time
            
            # Si no hay URL o cambió la URL
            if not srt_url or srt_url != self.last_srt_url:
                # Detener reproducción actual
                if self.ffmpeg_process:
                    self.stop_ffmpeg()
                    show_default_image()
                
                # Actualizar URL
                self.last_srt_url = srt_url
                
                if not srt_url:
                    register_device('NO REPRODUCIENDO')
                    log("STREAM", "warning", "No hay SRT configurado")
                    return
        
        # No intentar reproducir si no hay URL
        if not self.last_srt_url:
            show_default_image()
            register_device('NO REPRODUCIENDO')
            return
        
        # Solo iniciar FFmpeg si no está corriendo
        if not self.ffmpeg_process or self.ffmpeg_process.poll() is not None:
            self._start_ffmpeg(self.last_srt_url)

    def _start_output_monitor(self):
        """Monitorea la salida de FFmpeg en tiempo real"""
        def monitor():
            while self.ffmpeg_process and self.ffmpeg_process.poll() is None:
                # Leer stderr (donde FFmpeg escribe sus logs)
                err = self.ffmpeg_process.stderr.readline()
                if err:
                    err = err.strip()
                    if 'Connection refused' in err or 'Connection timed out' in err:
                        log("FFMPEG", "error", f"Error de conexión SRT: {err}")
                    elif 'Error' in err or 'error' in err:
                        log("FFMPEG", "error", f"Error FFmpeg: {err}")
                    elif 'Opening' in err or 'Stream mapping' in err:
                        log("FFMPEG", "info", err)
                    else:
                        log("FFMPEG", "debug", err)

                # Verificar si FFmpeg sigue vivo
                if self.ffmpeg_process.poll() is not None:
                    log("FFMPEG", "error", f"FFmpeg terminó con código: {self.ffmpeg_process.returncode}")
                    break

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start() 