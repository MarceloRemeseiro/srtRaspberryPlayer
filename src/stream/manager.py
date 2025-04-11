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
        self.kill_timeout = 5  # segundos para matar FFmpeg
        self.connection_timeout = 10  # Tiempo máximo para esperar conexión SRT

    def stop_ffmpeg(self):
        """Detiene FFmpeg de forma más eficiente"""
        if self.ffmpeg_process:
            try:
                log("FFMPEG", "info", "Deteniendo FFmpeg")
                self.ffmpeg_process.terminate()
                
                # Esperar un tiempo razonable para que termine
                start_time = time.time()
                while time.time() - start_time < self.kill_timeout:
                    if self.ffmpeg_process.poll() is not None:
                        break
                    time.sleep(0.1)
                
                # Si no ha terminado, lo matamos
                if self.ffmpeg_process.poll() is None:
                    self.ffmpeg_process.kill()
                    self.ffmpeg_process.wait()
                
                show_default_image()  # Mostrar imagen por defecto al detener
                
            except Exception as e:
                log("FFMPEG", "error", f"Error deteniendo FFmpeg: {e}")
            finally:
                self.ffmpeg_process = None

    def stream_video(self):
        current_time = time.time()
        
        # Reducir el intervalo de verificación a 2 segundos
        if current_time - self.last_config_check > 2:
            log("STREAM", "info", "Verificando configuración")
            srt_url = get_srt_url()
            self.last_config_check = current_time
            
            if not srt_url:
                if self.last_srt_url is not None:
                    log("STREAM", "warning", "Sin URL SRT configurada")
                    self.last_srt_url = None
                    self.stop_ffmpeg()
                    show_default_image()
                    register_device('NO REPRODUCIENDO')
                return
            
            if srt_url != self.last_srt_url:
                log("STREAM", "info", f"Nueva URL detectada")
                self.last_srt_url = srt_url
                self._start_ffmpeg(srt_url)
            else:
                if self.last_srt_url is not None:
                    log("STREAM", "warning", "URL SRT removida")
                    self.last_srt_url = None
                    self.stop_ffmpeg()
                    show_default_image()
                    register_device('NO REPRODUCIENDO')
        
        # Verificar si FFmpeg sigue vivo
        if self.ffmpeg_process and self.ffmpeg_process.poll() is not None:
            log("FFMPEG", "warning", "FFmpeg terminó inesperadamente")
            show_default_image()
            register_device('NO REPRODUCIENDO')
            self.ffmpeg_process = None
            # Intentar reiniciar si tenemos URL
            if self.last_srt_url:
                self._start_ffmpeg(self.last_srt_url)

    def _start_ffmpeg(self, srt_url):
        """Inicia FFmpeg con la URL dada"""
        try:
            # Asegurarnos que no haya instancia anterior
            self.stop_ffmpeg()
            
            log("STREAM", "info", f"Iniciando reproducción SRT: {srt_url}")
            
            ffmpeg_cmd = [
                'ffmpeg',
                '-loglevel', 'warning',     # Reducir logs innecesarios
                '-fflags', 'nobuffer',
                '-flags', 'low_delay',
                '-i', srt_url,
                '-vf', 'scale=1920:1080',
                '-pix_fmt', 'rgb565',
                '-f', 'fbdev',
                '-y', '/dev/fb0',
                '-f', 'alsa',
                '-ac', '2',
                '-ar', '48000',
                'default'
            ]
            
            self.ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Esperar a que FFmpeg conecte o falle
            start_time = time.time()
            while time.time() - start_time < self.connection_timeout:
                if self.ffmpeg_process.poll() is not None:
                    # FFmpeg terminó, probablemente error
                    error = self.ffmpeg_process.stderr.read()
                    log("FFMPEG", "error", f"FFmpeg falló: {error}")
                    show_default_image()
                    register_device('NO REPRODUCIENDO')
                    self.ffmpeg_process = None
                    return False
                
                # Verificar si hay datos en stderr
                error_line = self.ffmpeg_process.stderr.readline()
                if error_line:
                    if "Connection refused" in error_line or "Failed to connect" in error_line:
                        log("FFMPEG", "error", "No se pudo conectar al stream SRT")
                        self.stop_ffmpeg()
                        show_default_image()
                        return False
                    elif "Stream mapping" in error_line:
                        # FFmpeg conectó exitosamente
                        log("FFMPEG", "success", "Stream SRT conectado")
                        register_device('REPRODUCIENDO')
                        return True
                
                time.sleep(0.1)
            
            # Si llegamos aquí, timeout
            log("FFMPEG", "error", "Timeout esperando conexión SRT")
            self.stop_ffmpeg()
            show_default_image()
            return False
            
        except Exception as e:
            log("FFMPEG", "error", f"Error iniciando FFmpeg: {e}")
            show_default_image()
            register_device('NO REPRODUCIENDO')
            self.ffmpeg_process = None
            return False

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