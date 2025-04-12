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
            
            # Intentar configurar salida HDMI
            try:
                # Configurar audio para HDMI (3 = HDMI, 2 = HDMI1, 1 = Analógico)
                log("AUDIO", "info", "Configurando salida de audio HDMI...")
                subprocess.run(['amixer', 'cset', 'numid=3', '2'], check=False, 
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                # Establecer volumen al máximo
                subprocess.run(['amixer', 'set', 'Master', '100%'], check=False,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except Exception as e:
                log("AUDIO", "warning", f"Error configurando audio HDMI: {e}")
                
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
            
            # Probar dispositivos disponibles
            devices = ['default', 'hw:0,0', 'hw:0,1', 'hw:CARD=b835,DEV=0', 'plughw:0,0']
            for device in devices:
                log("AUDIO", "info", f"Verificando dispositivo: {device}")
            
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

    def _test_local_video(self):
        """Probar reproducción con un video local de prueba"""
        log("VIDEO", "info", "Intentando reproducir video local de prueba...")
        
        try:
            # Crear un video de prueba
            create_cmd = [
                'ffmpeg',
                '-f', 'lavfi',
                '-i', 'testsrc=duration=10:size=640x480:rate=30',
                '-c:v', 'libx264',
                '-y', '/tmp/test.mp4'
            ]
            
            subprocess.run(create_cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            
            # Reproducir el video generado
            play_cmd = [
                'ffmpeg',
                '-re',
                '-i', '/tmp/test.mp4',
                '-pix_fmt', 'rgb565',
                '-f', 'fbdev',
                '-y', '/dev/fb0'
            ]
            
            log("VIDEO", "info", "Reproduciendo video de prueba...")
            result = subprocess.run(play_cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            
            if result.returncode == 0:
                log("VIDEO", "success", "Reproducción de video local exitosa")
                return True
            else:
                log("VIDEO", "error", f"Error reproduciendo video local: {result.stderr.decode()}")
                return False
        except Exception as e:
            log("VIDEO", "error", f"Excepción reproduciendo video local: {str(e)}")
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
        
        # Si tenemos más de 3 intentos fallidos, probar con video local
        if self.failed_attempts >= 3:
            log("FFMPEG", "warning", "Demasiados intentos fallidos, reiniciando contador y volviendo a intentar")
            # Reiniciar contador
            self.failed_attempts = 0
            return
        
        # URL SRT fija que sabemos que funciona
        # Formato SRT con streamid (necesario) pero sin otros parámetros
        fixed_srt_url = "srt://core.streamingpro.es:6000/?mode=caller&transtype=live&streamid=7bb5ff4b-9470-4ff0-b5ff-16af476e8c1f,mode:request"
        
        # Si FFmpeg no está corriendo, iniciarlo
        if not self.ffmpeg_process or (self.ffmpeg_process and self.ffmpeg_process.poll() is not None):
            log("STREAM", "info", f"Iniciando reproducción con URL básica: {fixed_srt_url}")
            
            try:
                # Configuración optimizada para estabilidad, sólo opciones compatibles
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-loglevel', 'debug',          # Log detallado para diagnóstico
                    '-protocol_whitelist', 'file,udp,rtp,srt',  # Permitir protocolo SRT
                    # Aumentar buffer para mayor estabilidad
                    '-buffer_size', '16384k',      # Buffer grande
                    '-fflags', '+genpts+ignidx',   # Generar timestamps
                    # Quitar opciones incompatibles: srt_maxbw, srt_latency
                    '-i', fixed_srt_url,
                    # Evitar filtros innecesarios para reducir carga de CPU
                    '-pix_fmt', 'rgb565',
                    '-f', 'fbdev',
                    '-framedrop',                  # Permitir descartar frames para mantener sincronización
                    '-y', '/dev/fb0'
                ]
                
                # Añadir salida de audio si está disponible
                if self.has_audio:
                    log("FFMPEG", "info", "Añadiendo salida de audio...")
                    ffmpeg_cmd.extend([
                        '-f', 'alsa',
                        '-ac', '2',                # 2 canales
                        '-ar', '44100',            # Frecuencia de muestreo
                        # Opciones de sincronización audio-video
                        '-async', '1',             # Sincronización simple
                        # La opción alsa_buffer_size puede no ser compatible,
                        # usar buffer_size normal de ALSA
                        'default'                  # Dispositivo predeterminado
                    ])
                else:
                    # Desactivar audio si no hay dispositivo
                    ffmpeg_cmd.append('-an')
                    log("FFMPEG", "warning", "Audio desactivado (no hay dispositivo disponible)")
                
                log("FFMPEG", "debug", f"Comando: {' '.join(ffmpeg_cmd)}")
                
                self.ffmpeg_process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                
                log("FFMPEG", "success", "Proceso iniciado")
                
                # Iniciar monitoreo
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
            min_stable_time = 30  # Considerar estable si funciona más de 30 segundos
            
            # Recolectar todos los errores para diagnóstico
            all_errors = []
            
            # Primeras líneas de salida para diagnóstico
            initial_output = []
            got_initial_output = False
            
            while self.ffmpeg_process and self.ffmpeg_process.poll() is None:
                # Leer stderr (donde FFmpeg escribe sus logs)
                err = self.ffmpeg_process.stderr.readline()
                if err:
                    err = err.strip()
                    
                    # Recopilar primeras 10 líneas
                    if not got_initial_output and len(initial_output) < 10:
                        initial_output.append(err)
                        log("FFMPEG", "debug", f"Salida: {err}")
                    elif not got_initial_output:
                        got_initial_output = True
                        log("FFMPEG", "info", "Iniciada captura de salida")
                    
                    # Registrar errores para diagnóstico - excluir errores comunes de decode_slice_header
                    if 'error' in err.lower() and 'decode_slice_header' not in err:
                        all_errors.append(err)
                        log("FFMPEG", "error", err)
                    
                    # Salidas específicas para depuración
                    if 'frame=' in err:
                        try:
                            frame_count += 1
                            # Mostrar info de frames cada 5 segundos
                            current_time = time.time()
                            if current_time - last_status_time > 5:
                                log("FFMPEG", "info", f"Reproduciendo: {err}")
                                last_status_time = current_time
                        except:
                            pass
                    elif ('audio:' in err.lower() or 'video:' in err.lower() or 
                          'stream mapping:' in err.lower() or 'input #0' in err.lower()):
                        log("FFMPEG", "info", err)
                
                # Dormir para reducir uso de CPU
                time.sleep(0.1)
            
            # Cuando termine, mostrar diagnóstico
            if self.ffmpeg_process:
                running_time = time.time() - start_time
                
                # Mostrar código de salida para diagnóstico
                exit_code = self.ffmpeg_process.poll() or 0
                log("FFMPEG", "info", f"Proceso terminado con código {exit_code} después de {int(running_time)}s y {frame_count} frames")
                
                # Mostrar errores capturados (solo los más relevantes)
                if all_errors:
                    log("FFMPEG", "error", f"Se capturaron {len(all_errors)} errores, los últimos 3:")
                    for err in all_errors[-3:]:
                        log("FFMPEG", "error", f" - {err}")
                
                # Incrementar contador de intentos fallidos solo si falló demasiado pronto
                if frame_count == 0 or running_time < min_stable_time:
                    self.failed_attempts += 1
                    log("FFMPEG", "warning", f"Intento fallido #{self.failed_attempts} - Duración insuficiente ({int(running_time)}s)")
                else:
                    # Si reprodujo frames durante un tiempo razonable, reiniciar contador
                    self.failed_attempts = 0
                    log("FFMPEG", "info", f"Reproducción estable durante {int(running_time)}s con {frame_count} frames")
                
                self.ffmpeg_process = None
                
                # Esperar más tiempo antes de reiniciar si ha funcionado bien
                if running_time >= min_stable_time:
                    delay = 5
                    log("FFMPEG", "info", f"Esperando {delay}s antes de reiniciar...")
                    time.sleep(delay)
                else:
                    # Esperar poco si falló rápido
                    time.sleep(2)
                
                # Reiniciar reproducción automáticamente
                self.stream_video()
                
        thread = threading.Thread(target=simple_monitor, daemon=True)
        thread.start() 