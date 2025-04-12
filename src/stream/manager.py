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
                    '-fflags', '+discardcorrupt+igndts',  # Descartar paquetes corruptos
                    '-err_detect', 'ignore_err',  # Ignorar errores
                    '-analyzeduration', '2000000',  # Aumentar duración de análisis
                    '-timeout', '5000000',  # Timeout para SRT
                    '-i', fixed_srt_url,
                    '-threads', '4',  # Usar 4 hilos para decodificación
                ]
                
                # Intentar con decodificador hardware si está disponible
                try:
                    # Verificar si el decodificador hardware está disponible
                    hw_check = subprocess.run(
                        ['ffmpeg', '-codecs'], 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE, 
                        text=True
                    )
                    
                    if 'h264_v4l2m2m' in hw_check.stdout:
                        log("FFMPEG", "info", "Usando decodificador hardware h264_v4l2m2m")
                        ffmpeg_cmd.extend(['-c:v', 'h264_v4l2m2m'])
                    else:
                        log("FFMPEG", "info", "Decodificador hardware no disponible, usando software")
                except:
                    log("FFMPEG", "info", "Error verificando decodificadores, usando software")
                
                # Añadir opciones de video
                ffmpeg_cmd.extend([
                    '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2',  # Forzar pantalla completa
                    '-pix_fmt', 'rgb565',
                    '-f', 'fbdev',
                    '-y', '/dev/fb0'
                ])
                
                # Añadir audio si está disponible
                if self.has_audio:
                    # Probar diferentes configuraciones de audio
                    log("FFMPEG", "info", "Configurando salida de audio...")
                    
                    # Opción 1: Usar dispositivo default
                    ffmpeg_cmd.extend([
                        '-f', 'alsa',
                        '-ac', '2',     # 2 canales
                        '-ar', '44100', # Frecuencia de muestreo
                        'default'       # Dispositivo predeterminado
                    ])
                    log("FFMPEG", "info", "Usando dispositivo de audio: default")
                    
                    # Alternativa si la configuración anterior falla:
                    # ffmpeg_cmd.extend([
                    #     '-f', 'alsa',
                    #     '-device_name', 'hw:0,0',
                    #     '-ac', '2',
                    #     '-ar', '44100',
                    #     'hw:0,0'
                    # ])
                else:
                    # Desactivar audio si no hay dispositivo
                    ffmpeg_cmd.append('-an')
                    log("FFMPEG", "warning", "Reproduciendo sin audio (no hay dispositivo disponible)")
                
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
            frame_count = 0
            start_time = time.time()
            last_status_time = 0
            
            while self.ffmpeg_process and self.ffmpeg_process.poll() is None:
                # Leer stderr (donde FFmpeg escribe sus logs)
                err = self.ffmpeg_process.stderr.readline()
                if err:
                    err = err.strip()
                    
                    if 'frame=' in err:
                        # Es una línea de progreso, actualizar contador
                        try:
                            frame_count += 1
                            current_time = time.time()
                            
                            # Mostrar estado cada 5 segundos
                            if current_time - last_status_time > 5:
                                log("FFMPEG", "info", f"Reproduciendo: {err}")
                                last_status_time = current_time
                        except:
                            pass
                    elif 'error' in err.lower() and 'decode_slice_header error' not in err:
                        # Error importante (ignorar errores repetitivos de slice_header)
                        log("FFMPEG", "error", err)
                    elif 'audio:' in err.lower() or 'video:' in err.lower() or 'stream mapping:' in err.lower():
                        # Información relevante
                        log("FFMPEG", "info", err)
                
                # Dormir para reducir uso de CPU
                time.sleep(0.1)
            
            # Cuando termine, reiniciar automáticamente
            if self.ffmpeg_process:
                running_time = time.time() - start_time
                log("FFMPEG", "info", f"Proceso terminado después de {int(running_time)}s y {frame_count} frames")
                self.ffmpeg_process = None
                
                # Esperar 2 segundos antes de reiniciar
                time.sleep(2)
                
                # Reiniciar reproducción automáticamente
                self.stream_video()
                
        thread = threading.Thread(target=simple_monitor, daemon=True)
        thread.start() 