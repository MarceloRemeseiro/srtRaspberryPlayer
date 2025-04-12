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
        self.last_ffmpeg_start = 0  # Timestamp del último inicio de FFmpeg
        self.failed_attempts = 0    # Contador de intentos fallidos consecutivos
        self.has_audio = self._check_audio_device()
        self.has_framebuffer = self._check_framebuffer()
        self.use_hw_decoder = False  # Inicialmente usar decodificador por software
        
        # Probar la capacidad de video al inicio
        if self.has_framebuffer:
            self._test_video_output()

    def _check_audio_device(self):
        """Verifica si hay dispositivos de audio disponibles"""
        try:
            # Comprobar si existe /dev/snd
            if not os.path.exists('/dev/snd'):
                log("AUDIO", "warning", "No se encontró /dev/snd, intentando cargar el módulo de sonido")
                # Intentar cargar el módulo de sonido Raspberry Pi
                try:
                    subprocess.run(['modprobe', 'snd-bcm2835'], check=True)
                    log("AUDIO", "info", "Módulo snd-bcm2835 cargado")
                    # Dar tiempo a que se inicialice
                    time.sleep(1)
                except Exception as e:
                    log("AUDIO", "error", f"Error cargando módulo de sonido: {e}")
                
                # Verificar de nuevo si existe /dev/snd después de cargar el módulo
                if not os.path.exists('/dev/snd'):
                    log("AUDIO", "warning", "Aún no se encuentra /dev/snd")
                    return False
                
            # Intentar obtener dispositivos de audio
            result = subprocess.run(['aplay', '-l'], 
                                    stdout=subprocess.PIPE, 
                                    stderr=subprocess.PIPE, 
                                    text=True)
            
            if "no soundcards found" in result.stderr:
                log("AUDIO", "warning", "No se encontraron dispositivos de audio")
                return False
                
            # Si llegamos aquí, hay dispositivos de audio
            log("AUDIO", "info", f"Dispositivos de audio encontrados: {result.stdout.strip()}")
            return True
            
        except Exception as e:
            log("AUDIO", "error", f"Error verificando dispositivos de audio: {e}")
            return False

    def _check_framebuffer(self):
        """Verifica si el framebuffer está disponible"""
        if os.path.exists('/dev/fb0'):
            log("VIDEO", "info", "Framebuffer detectado: /dev/fb0")
            return True
        else:
            log("VIDEO", "error", "Framebuffer no encontrado")
            return False
            
    def _test_video_output(self):
        """Realiza una prueba básica de salida de video"""
        try:
            log("VIDEO", "info", "Realizando prueba de video...")
            # Intentar mostrar un patrón de color con ffmpeg
            cmd = [
                'ffmpeg', 
                '-loglevel', 'error',
                '-f', 'lavfi', 
                '-i', 'color=c=blue:s=1280x720:d=3', 
                '-pix_fmt', 'rgb565',
                '-f', 'fbdev', 
                '-y', '/dev/fb0'
            ]
            
            result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
            
            if result.returncode == 0:
                log("VIDEO", "success", "Prueba de video exitosa")
                return True
            else:
                log("VIDEO", "error", f"Error en prueba de video: {result.stderr}")
                return False
                
        except Exception as e:
            log("VIDEO", "error", f"Error realizando prueba de video: {e}")
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
        current_time = time.time()
        
        # Verificar si el framebuffer está disponible
        if not self.has_framebuffer:
            self.has_framebuffer = self._check_framebuffer()
            if not self.has_framebuffer:
                log("VIDEO", "error", "No se puede reproducir sin framebuffer")
                time.sleep(10)
                return
        
        # URL SRT fija que sabemos que funciona
        fixed_srt_url = "srt://core.streamingpro.es:6000/?mode=caller&transtype=live&streamid=7bb5ff4b-9470-4ff0-b5ff-16af476e8c1f,mode:request"
        
        # Si FFmpeg no está corriendo, iniciarlo
        if not self.ffmpeg_process or (self.ffmpeg_process and self.ffmpeg_process.poll() is not None):
            log("STREAM", "info", f"Iniciando reproducción con URL fija: {fixed_srt_url}")
            
            try:
                # Comando FFmpeg simple 
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-loglevel', 'info',
                    '-protocol_whitelist', 'file,udp,rtp,srt',  # Permitir protocolo SRT
                    '-fflags', '+discardcorrupt',  # Descartar paquetes corruptos
                    '-analyzeduration', '2000000',  # Aumentar duración de análisis
                    '-i', fixed_srt_url,
                    '-vf', 'scale=1280:720',
                    '-pix_fmt', 'rgb565',
                    '-f', 'fbdev',
                    '-y', '/dev/fb0'
                ]
                
                # Desactivar audio para simplificar
                ffmpeg_cmd.append('-an')
                
                # Mostrar el comando completo para depuración
                log("FFMPEG", "debug", f"Comando: {' '.join(ffmpeg_cmd)}")
                
                self.ffmpeg_process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                
                log("FFMPEG", "success", "Proceso iniciado")
                
                # Iniciar monitoreo básico
                self._start_simple_monitor()
                
            except Exception as e:
                log("FFMPEG", "error", f"Error iniciando proceso: {e}")
                self.ffmpeg_process = None

    def _start_simple_monitor(self):
        """Monitoreo simplificado de la salida"""
        def simple_monitor():
            while self.ffmpeg_process and self.ffmpeg_process.poll() is None:
                # Solo leer y mostrar errores importantes
                err = self.ffmpeg_process.stderr.readline()
                if err and 'error' in err.lower():
                    log("FFMPEG", "error", err.strip())
                
                # Dormir para reducir uso de CPU
                time.sleep(0.1)
            
            # Cuando termine, reiniciar automáticamente
            if self.ffmpeg_process:
                log("FFMPEG", "info", "Proceso terminado, reiniciando...")
                self.ffmpeg_process = None
                
                # Esperar 2 segundos antes de reiniciar
                time.sleep(2)
                
                # Reiniciar reproducción automáticamente
                self.stream_video()
                
        thread = threading.Thread(target=simple_monitor, daemon=True)
        thread.start() 