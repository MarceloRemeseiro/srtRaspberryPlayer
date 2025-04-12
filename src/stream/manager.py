import time
import subprocess
import threading
import os
from config.settings import CONFIG_CHECK_INTERVAL
from display.screen import show_default_image
from network.client import register_device, get_srt_url, log

class StreamManager:
    def __init__(self):
        self.ffmpeg_process = None
        self.last_config_check = time.time()
        self.last_srt_url = None
        self.failed_attempts = 0
        self.has_audio = self._check_audio_device()
        self.has_framebuffer = os.path.exists('/dev/fb0')
        
        if self.has_framebuffer:
            log("VIDEO", "info", "Framebuffer detectado: /dev/fb0")
        else:
            log("VIDEO", "error", "Framebuffer no encontrado")

    def _check_audio_device(self):
        """Verifica si hay dispositivos de audio disponibles mediante ALSA"""
        try:
            log("AUDIO", "info", "Verificando ALSA para audio HDMI...")
            
            # Configurar HDMI como salida principal
            subprocess.run(['amixer', 'cset', 'numid=3', '2'], 
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            log("AUDIO", "info", "HDMI configurado como salida principal")
            
            # Establecer volumen al máximo
            subprocess.run(['amixer', 'set', 'Master', '100%'], 
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            log("AUDIO", "info", "Volumen configurado al máximo")
            
            return True
            
        except Exception as e:
            log("AUDIO", "error", f"Error verificando dispositivos de audio: {e}")
            return False

    def stop_ffmpeg(self):
        if self.ffmpeg_process:
            log("FFMPEG", "info", "Deteniendo FFmpeg")
            try:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait(timeout=3)
            except Exception as e:
                log("FFMPEG", "error", f"Error deteniendo FFmpeg: {e}")
                try:
                    self.ffmpeg_process.kill()
                except:
                    pass
            self.ffmpeg_process = None

    def stream_video(self):
        # Obtener la URL SRT del servidor
        srt_url = get_srt_url()
        if not srt_url:
            log("STREAM", "warning", "No hay URL SRT disponible. Reintentando en 10 segundos...")
            show_default_image()
            time.sleep(10)
            return
        
        # Guardar la última URL SRT para reutilizarla en caso de reconexión
        self.last_srt_url = srt_url
        
        # Si FFmpeg no está corriendo, iniciarlo
        if not self.ffmpeg_process or (self.ffmpeg_process and self.ffmpeg_process.poll() is not None):
            log("STREAM", "info", f"Iniciando reproducción con SRT URL: {srt_url}")
            
            try:
                # Configurar HDMI como salida antes de iniciar FFmpeg
                subprocess.run(['amixer', 'cset', 'numid=3', '2'], 
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                log("AUDIO", "info", "HDMI configurado como salida de audio")
                
                # Asegurar que el volumen está al máximo
                subprocess.run(['amixer', 'set', 'Master', '100%'],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                log("AUDIO", "info", "Volumen configurado al 100%")
                
                # Comando FFmpeg optimizado con sincronización de audio/video
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-loglevel', 'warning',
                    '-stats',
                    '-i', srt_url,
                    # Parámetros de sincronización mejorados
                    '-vsync', '1',
                    '-async', '1',
                    # Mapeo explícito de streams
                    '-map', '0:v:0',
                    '-map', '0:a:0',
                    # Video con resolución 1080p
                    '-s', '1920x1080',
                    '-pix_fmt', 'rgb24',  # Mejor calidad de color que rgb565
                    '-f', 'fbdev',
                    '/dev/fb0',
                    # Audio siempre habilitado
                    '-af', 'aresample=async=1000',
                    '-f', 'alsa',
                    '-ac', '2',
                    'sysdefault:CARD=vc4hdmi0'
                ]
                
                log("FFMPEG", "info", f"Comando: {' '.join(ffmpeg_cmd)}")
                
                # Iniciar proceso de FFmpeg
                self.ffmpeg_process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                
                # Monitoreo simple en un hilo separado
                threading.Thread(
                    target=self._monitor_ffmpeg,
                    daemon=True
                ).start()
                
            except Exception as e:
                log("FFMPEG", "error", f"Error iniciando FFmpeg: {e}")
                self.ffmpeg_process = None
    
    def _monitor_ffmpeg(self):
        """Monitoreo simplificado para el proceso FFmpeg"""
        start_time = time.time()
        
        # Esperar a que el proceso termine
        self.ffmpeg_process.wait()
        
        # Procesar resultado
        running_time = int(time.time() - start_time)
        exit_code = self.ffmpeg_process.returncode
        log("FFMPEG", "info", f"FFmpeg terminado con código {exit_code} después de {running_time}s")
        
        # Reintentar con espera progresiva si falló rápidamente
        if running_time < 5:
            self.failed_attempts += 1
            wait_time = min(30, 5 * self.failed_attempts)
            log("FFMPEG", "info", f"Intento fallido #{self.failed_attempts}, esperando {wait_time}s antes de reintentar")
            time.sleep(wait_time)
        else:
            self.failed_attempts = 0
        
        # Limpiar y reiniciar
        self.ffmpeg_process = None
        self.stream_video()

    def run(self):
        """Bucle principal de ejecución"""
        while True:
            try:
                # Iniciar la reproducción si no está en curso
                if not self.ffmpeg_process or (self.ffmpeg_process and self.ffmpeg_process.poll() is not None):
                    self.stream_video()
                
                # Verificar periódicamente cambios en la URL
                current_time = time.time()
                if current_time - self.last_config_check > CONFIG_CHECK_INTERVAL:
                    self.last_config_check = current_time
                    
                    new_srt_url = get_srt_url()
                    if new_srt_url != self.last_srt_url:
                        log("SISTEMA", "info", "La URL SRT ha cambiado, reiniciando reproducción...")
                        self.stop_ffmpeg()
                        time.sleep(1)
                        self.stream_video()
                
                # Dormir para no consumir CPU
                time.sleep(5)
                
            except Exception as e:
                log("SISTEMA", "error", f"Error en bucle principal: {e}")
                time.sleep(10) 