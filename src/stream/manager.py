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
        # Formato SRT estándar
        fixed_srt_url = "srt://core.streamingpro.es:6000?streamid=7bb5ff4b-9470-4ff0-b5ff-16af476e8c1f&mode=caller&transtype=live"
        
        # Si FFmpeg no está corriendo, iniciarlo
        if not self.ffmpeg_process or (self.ffmpeg_process and self.ffmpeg_process.poll() is not None):
            log("STREAM", "info", f"Iniciando reproducción con URL simplificada: {fixed_srt_url}")
            
            try:
                # Enfoque ultra minimalista - solo lo esencial
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-loglevel', 'debug',          # Log detallado para diagnóstico
                    '-protocol_whitelist', 'file,udp,rtp,srt',  # Permitir protocolo SRT
                    '-fflags', '+nobuffer+flush_packets',  # No almacenar en buffer
                    '-flags', 'low_delay',         # Minimizar latencia
                    '-strict', 'experimental',     # Permitir opciones experimentales
                    '-srt_streamid', '7bb5ff4b-9470-4ff0-b5ff-16af476e8c1f', # Forzar streamid
                    '-i', fixed_srt_url,
                    '-pix_fmt', 'rgb565',
                    '-f', 'fbdev',
                    '-y', '/dev/fb0',
                    '-an'                          # Sin audio
                ]
                
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
                    
                    # Registrar errores para diagnóstico
                    if 'error' in err.lower():
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
                
                # Mostrar errores capturados
                if all_errors:
                    log("FFMPEG", "error", f"Se capturaron {len(all_errors)} errores, los últimos 3:")
                    for err in all_errors[-3:]:
                        log("FFMPEG", "error", f" - {err}")
                
                # Incrementar contador de intentos fallidos si no se reprodujo ningún frame
                if frame_count == 0:
                    self.failed_attempts += 1
                    log("FFMPEG", "warning", f"Intento fallido #{self.failed_attempts} - No se reprodujo ningún frame")
                else:
                    # Si reprodujo frames, reiniciar contador
                    self.failed_attempts = 0
                
                self.ffmpeg_process = None
                
                # Esperar 2 segundos antes de reiniciar
                time.sleep(2)
                
                # Reiniciar reproducción automáticamente
                self.stream_video()
                
        thread = threading.Thread(target=simple_monitor, daemon=True)
        thread.start() 