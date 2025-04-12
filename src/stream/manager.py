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
                time.sleep(10)  # Esperar 10 segundos antes de volver a verificar
                return
                
        if current_time - self.last_config_check > CONFIG_CHECK_INTERVAL:
            log("STREAM", "info", f"Verificando configuración después de {CONFIG_CHECK_INTERVAL} segundos")
            
            # Obtener URL SRT actualizada
            srt_url = get_srt_url()
            self.last_config_check = current_time
            
            # Registrar la consulta
            log("STREAM", "info", f"Estado de SRT_URL: {srt_url}")
            
            # Si hay una nueva URL SRT
            if srt_url:
                log("STREAM", "info", f"URL SRT disponible: {srt_url}")
                if srt_url != self.last_srt_url:
                    log("STREAM", "info", "Nueva URL SRT detectada, reiniciando reproducción")
                    self.stop_ffmpeg()
                    self.last_srt_url = srt_url
                    # Reiniciar contador de intentos si la URL cambia
                    self.failed_attempts = 0
            else:
                # Si no hay URL, detener reproducción
                if self.ffmpeg_process:
                    log("STREAM", "info", "No hay URL SRT, deteniendo reproducción")
                    self.stop_ffmpeg()
                self.last_srt_url = None
                show_default_image()
                register_device('NO REPRODUCIENDO')
                self.failed_attempts = 0  # Reiniciar contador
                return
        
        # Si tenemos URL SRT pero ffmpeg no está corriendo, iniciarlo
        # Añadir protección para evitar reinicios frecuentes
        if (self.last_srt_url and 
            self.has_framebuffer and  # Solo intentar si hay framebuffer
            (not self.ffmpeg_process or 
             (self.ffmpeg_process and self.ffmpeg_process.poll() is not None)) and
            (current_time - self.last_ffmpeg_start > 5) and  # Esperar al menos 5 segundos entre reinicios
            self.failed_attempts < 3):  # Limitar a 3 intentos fallidos consecutivos
            
            log("STREAM", "info", f"Iniciando reproducción con URL: {self.last_srt_url} (intento {self.failed_attempts+1}/3)")
            try:
                # Actualizar timestamp antes de iniciar
                self.last_ffmpeg_start = current_time
                
                # Configuración básica de FFmpeg que debería funcionar en cualquier Pi
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-loglevel', 'info',
                    '-protocol_whitelist', 'file,udp,rtp,srt',  # Permitir protocolo SRT
                    '-buffer_size', '8192k',     # Aumentar tamaño del búfer
                ]
                
                # Si estamos en el tercer intento, probar con decodificador hardware
                if self.failed_attempts >= 2 and not self.use_hw_decoder:
                    log("FFMPEG", "info", "Probando con decodificador hardware h264_v4l2m2m")
                    self.use_hw_decoder = True
                    ffmpeg_cmd.extend([
                        '-c:v', 'h264_v4l2m2m',  # Usar decodificador hardware
                    ])
                
                ffmpeg_cmd.extend([
                    '-i', self.last_srt_url,
                    '-strict', 'experimental',  # Permitir decodificadores experimentales
                    '-vf', 'scale=1280:720',
                    '-pix_fmt', 'rgb565',
                    '-f', 'fbdev',
                    '-framerate', '25',
                    '-timeout', '5000000',      # Establecer timeout
                    '-max_delay', '500000',     # Reducir el retardo máximo
                    '-fflags', '+genpts+discardcorrupt',  # Generar PTS y descartar frames corruptos
                    '-analyzeduration', '10000000',  # Aumentar tiempo de análisis
                    '-probesize', '5000000',    # Aumentar buffer de sondeo
                    '-stats',                   # Mostrar estadísticas
                    '-re',                      # Leer a velocidad nativa
                    '-y', '/dev/fb0'
                ])
                
                # Añadir audio solo si está disponible
                if not self.has_audio:
                    ffmpeg_cmd.append('-an')  # Desactivar audio
                    log("FFMPEG", "warning", "Reproduciendo sin audio (no hay dispositivo disponible)")
                else:
                    ffmpeg_cmd.extend([
                        '-f', 'alsa',
                        '-ac', '2',
                        '-ar', '48000',
                        'hw:0,0'  # Usar directamente el hardware en lugar de 'default'
                    ])
                    log("FFMPEG", "info", "Reproduciendo con audio (dispositivo hw:0,0)")
                
                # Añadir información para depuración
                log("FFMPEG", "debug", f"Comando FFmpeg: {' '.join(ffmpeg_cmd)}")
                
                self.ffmpeg_process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                
                log("FFMPEG", "success", "Proceso iniciado")
                register_device('REPRODUCIENDO')
                
                # Iniciar monitoreo de salida
                self._start_output_monitor()
                
            except Exception as e:
                log("FFMPEG", "error", f"Error iniciando proceso: {e}")
                show_default_image()
                register_device('NO REPRODUCIENDO')
                self.ffmpeg_process = None
                self.failed_attempts += 1
        elif self.failed_attempts >= 3 and current_time - self.last_ffmpeg_start > 30:
            # Reintentar después de 30 segundos en pausa
            log("STREAM", "warning", "Demasiados intentos fallidos. Reiniciando contador después de 30s")
            self.failed_attempts = 0
            self.last_ffmpeg_start = 0

    def _start_output_monitor(self):
        """Monitorea la salida de FFmpeg en tiempo real"""
        def monitor():
            start_time = time.time()
            error_count = 0
            last_error_time = 0
            
            while self.ffmpeg_process and self.ffmpeg_process.poll() is None:
                # Leer stderr (donde FFmpeg escribe sus logs)
                err = self.ffmpeg_process.stderr.readline()
                if err:
                    err = err.strip()
                    
                    # Registrar errores específicos de H264
                    if 'non-existing PPS' in err or 'decode_slice_header error' in err:
                        current_time = time.time()
                        
                        # Solo contar como error si ha pasado más de 2 segundos desde el último
                        if current_time - last_error_time > 2:
                            error_count += 1
                            last_error_time = current_time
                            
                            # Solo reportar cada 20 errores para no saturar los logs
                            if error_count % 20 == 0:
                                log("FFMPEG", "warning", f"Errores de decodificación H264: {error_count} acumulados")
                        
                    elif 'Connection refused' in err or 'Connection timed out' in err:
                        log("FFMPEG", "error", f"Error de conexión SRT: {err}")
                    elif 'Error' in err or 'error' in err:
                        if 'non-existing PPS' not in err and 'decode_slice_header error' not in err:
                            log("FFMPEG", "error", f"Error FFmpeg: {err}")
                    elif 'Opening' in err or 'Stream mapping' in err or 'Video:' in err or 'Audio:' in err:
                        log("FFMPEG", "info", err)
                    elif 'frame=' in err:  # Línea de progreso
                        # Solo mostrar cada 50 frames
                        if not hasattr(monitor, 'frame_count'):
                            monitor.frame_count = 0
                        monitor.frame_count += 1
                        if monitor.frame_count % 50 == 0:
                            log("FFMPEG", "info", f"Progreso: {err}")
                    else:
                        log("FFMPEG", "debug", err)

                # Verificar si FFmpeg sigue vivo
                if self.ffmpeg_process.poll() is not None:
                    duration = time.time() - start_time
                    
                    # Si FFmpeg termina en menos de 5 segundos y tuvimos muchos errores, incrementar contador de fallos
                    if duration < 5 and error_count > 20:
                        self.failed_attempts += 1
                        log("FFMPEG", "error", f"FFmpeg terminó demasiado rápido: {self.ffmpeg_process.returncode} (intento {self.failed_attempts}/3)")
                    else:
                        # Si duró más de 5 segundos o hubo pocos errores, reiniciar contador
                        self.failed_attempts = 0
                        log("FFMPEG", "error", f"FFmpeg terminó con código: {self.ffmpeg_process.returncode} (después de {int(duration)} segundos)")
                    break

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start() 