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
        """Verifica si hay dispositivos de audio disponibles mediante ALSA"""
        try:
            log("AUDIO", "info", "Verificando ALSA para audio HDMI...")
            
            # Verificar dispositivos ALSA con aplay -L (más completo)
            try:
                alsa_devices = subprocess.run(['aplay', '-L'], 
                                           stdout=subprocess.PIPE, 
                                           stderr=subprocess.PIPE,
                                           text=True)
                
                if "hdmi:" in alsa_devices.stdout.lower():
                    hdmi_devices = [line for line in alsa_devices.stdout.split('\n') if "hdmi:" in line.lower()]
                    log("AUDIO", "success", f"Dispositivos HDMI encontrados: {', '.join(hdmi_devices)}")
                    
                    # Configurar HDMI como salida principal
                    subprocess.run(['amixer', 'cset', 'numid=3', '2'], 
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    log("AUDIO", "info", "HDMI configurado como salida principal")
                    
                    # Establecer volumen al máximo
                    subprocess.run(['amixer', 'set', 'Master', '100%'], 
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    log("AUDIO", "info", "Volumen configurado al máximo")
                    
                    return True
                else:
                    log("AUDIO", "warning", "No se encontró ningún dispositivo HDMI en ALSA")
            except Exception as e:
                log("AUDIO", "warning", f"Error verificando dispositivos ALSA: {e}")
            
            # Incluso si no pudimos verificar, asumimos que hay audio y lo intentamos
            log("AUDIO", "info", "Asumiendo que hay audio disponible")
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
        # Detener proceso principal
        if self.ffmpeg_process:
            log("FFMPEG", "info", "Deteniendo FFmpeg principal")
            try:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait(timeout=3)
            except Exception as e:
                log("FFMPEG", "error", f"Error deteniendo FFmpeg principal: {e}")
                try:
                    self.ffmpeg_process.kill()
                except:
                    pass
            self.ffmpeg_process = None
        
        # Detener proceso de audio si existe
        if hasattr(self, 'ffmpeg_audio_process') and self.ffmpeg_audio_process:
            log("FFMPEG", "info", "Deteniendo FFmpeg audio")
            try:
                self.ffmpeg_audio_process.terminate()
                self.ffmpeg_audio_process.wait(timeout=3)
            except Exception as e:
                log("FFMPEG", "error", f"Error deteniendo FFmpeg audio: {e}")
                try:
                    self.ffmpeg_audio_process.kill()
                except:
                    pass
            self.ffmpeg_audio_process = None

    def stream_video(self):
        current_time = time.time()
        
        # Verificar si el framebuffer está disponible
        if not self.has_framebuffer:
            self.has_framebuffer = self._check_framebuffer()
            if not self.has_framebuffer:
                log("VIDEO", "error", "No se puede reproducir sin framebuffer")
                time.sleep(10)
                return
        
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
            
            # Configurar HDMI como salida antes de iniciar FFmpeg
            try:
                # Asegurar HDMI como salida principal
                subprocess.run(['amixer', 'cset', 'numid=3', '2'], 
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                log("AUDIO", "info", "HDMI configurado como salida de audio antes de iniciar FFmpeg")
                
                # Asegurar que el volumen está al máximo
                subprocess.run(['amixer', 'set', 'Master', '100%'],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                log("AUDIO", "info", "Volumen configurado al 100%")
            except Exception as e:
                log("AUDIO", "warning", f"Error configurando HDMI como salida: {e}")
            
            try:
                # Modificamos la estrategia para resolver problemas de decodificación y ALSA
                
                # 1. Primero enfocarse solo en video, desactivando audio temporalmente
                # Esto permite verificar si la conexión SRT funciona correctamente
                log("FFMPEG", "info", "Intentando reproducción con solo video para probar conexión SRT")
                
                # Parámetros básicos para solo video (mayor estabilidad)
                video_solo_cmd = [
                    'ffmpeg',
                    # Nivel de log detallado para diagnóstico
                    '-loglevel', 'info',
                    # Parámetros SRT críticos incrustados en URL para mejor conexión
                    '-i', f"{srt_url}&latency=1000&tlpktdrop=0&nakreport=1",
                    # Opción clave para problemas de decodificación H264
                    '-err_detect', 'ignore_err',
                    # Usar decoder de software para mejor compatibilidad
                    '-c:v', 'h264',
                    # Saltar frames corruptos
                    '-skip_frame', 'noref',
                    # Decodificación más permisiva
                    '-flags2', '+ignorecrop',
                    # Indicar formato de salida para evitar errores de conversión
                    '-pix_fmt', 'rgb565',
                    # Salida a framebuffer
                    '-f', 'fbdev', 
                    '/dev/fb0'
                ]
                
                log("FFMPEG", "debug", f"Comando inicial (solo video): {' '.join(video_solo_cmd)}")
                
                # Iniciar proceso solo con video primero
                self.last_ffmpeg_start = time.time()
                self.ffmpeg_process = subprocess.Popen(
                    video_solo_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                
                # Verificar si se inició correctamente el video
                time.sleep(2)
                if self.ffmpeg_process.poll() is None:
                    log("FFMPEG", "success", "Proceso de solo video iniciado correctamente")
                    
                    # Si el video funciona por 3 segundos, intentar con audio
                    time.sleep(1)
                    if self.ffmpeg_process.poll() is None:
                        log("FFMPEG", "info", "Video estable, iniciando monitoreo...")
                        self._start_enhanced_monitor()
                    else:
                        # Si falló el video, intentar configuración alternativa SRT
                        log("FFMPEG", "warning", "El proceso solo video falló, probando parámetros SRT alternativos...")
                        error_output = ""
                        try:
                            error_output = self.ffmpeg_process.stderr.read(1000)
                        except:
                            pass
                        
                        log("FFMPEG", "error", f"Error inicial: {error_output}")
                        
                        # Intentar con parámetros SRT explícitos como opción separada
                        alt_srt_cmd = [
                            'ffmpeg',
                            '-loglevel', 'info',
                            # Formato SRT explícito  
                            '-f', 'srt',
                            # Opciones para ignorar errores
                            '-err_detect', 'ignore_err',
                            '-fflags', '+igndts+genpts+discardcorrupt',
                            # URL sin parámetros adicionales
                            '-i', srt_url,
                            # Evitar optimizaciones PTS para mejor compatibilidad
                            '-vsync', '0',
                            # Mapeado explícito
                            '-map', '0:v:0',
                            # Ignorar audio
                            '-an',
                            # Salida
                            '-pix_fmt', 'rgb565',
                            '-f', 'fbdev',
                            '/dev/fb0'
                        ]
                        
                        log("FFMPEG", "info", f"Comando alternativo SRT: {' '.join(alt_srt_cmd)}")
                        
                        # Iniciar proceso alternativo
                        self.ffmpeg_process = subprocess.Popen(
                            alt_srt_cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            universal_newlines=True
                        )
                        
                        # Verificar si se inició correctamente
                        time.sleep(2)
                        if self.ffmpeg_process.poll() is None:
                            log("FFMPEG", "success", "Proceso alternativo SRT iniciado correctamente")
                            self._start_enhanced_monitor()
                        else:
                            # Si ambos métodos fallan, intentar como última opción un enfoque más básico
                            log("FFMPEG", "error", "Ambos métodos SRT fallaron, intentando enfoque básico...")
                            
                            # Intentar con configuración mínima (último recurso)
                            minimal_cmd = [
                                'ffmpeg',
                                '-loglevel', 'info',
                                # Use timeout para cortar rápido si hay problemas
                                '-timeout', '5000000',
                                # Modo de espera indefinida para SRT si hay problemas
                                '-listen_timeout', '-1',
                                # SRT básico
                                '-i', srt_url,
                                # Salida directa sin procesar
                                '-c:v', 'copy',
                                '-an',
                                '-f', 'fbdev',
                                '/dev/fb0'
                            ]
                            
                            log("FFMPEG", "info", f"Comando mínimo: {' '.join(minimal_cmd)}")
                            
                            self.ffmpeg_process = subprocess.Popen(
                                minimal_cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                universal_newlines=True
                            )
                            
                            time.sleep(2)
                            if self.ffmpeg_process.poll() is None:
                                log("FFMPEG", "success", "Proceso mínimo iniciado correctamente")
                                self._start_enhanced_monitor()
                            else:
                                log("FFMPEG", "error", "Todos los métodos de reproducción fallaron")
                                error_output = ""
                                try:
                                    error_output = self.ffmpeg_process.stderr.read(1000)
                                except:
                                    pass
                                
                                log("FFMPEG", "error", f"Error final: {error_output}")
                                self.ffmpeg_process = None
                else:
                    log("FFMPEG", "error", "El proceso inicial falló inmediatamente")
                    error_output = ""
                    try:
                        error_output = self.ffmpeg_process.stderr.read(1000)
                    except:
                        pass
                    
                    log("FFMPEG", "error", f"Error: {error_output}")
                    self.ffmpeg_process = None
            except Exception as e:
                log("FFMPEG", "error", f"Error iniciando proceso FFmpeg: {e}")
                self.ffmpeg_process = None
                
    def _start_enhanced_monitor(self):
        """Monitoreo mejorado para FFmpeg con detección de errores avanzada"""
        def monitor():
            error_count = 0
            frame_count = 0
            start_time = time.time()
            last_status_time = 0
            last_frame_time = time.time()
            
            while self.ffmpeg_process and self.ffmpeg_process.poll() is None:
                # Leer la salida de error de FFmpeg
                try:
                    err = self.ffmpeg_process.stderr.readline()
                except Exception as e:
                    log("FFMPEG", "warning", f"Error leyendo stderr: {e}")
                    time.sleep(0.5)
                    continue
                
                if err:
                    err = err.strip()
                    current_time = time.time()
                    
                    # Detectar frames recibidos
                    if 'frame=' in err:
                        frame_count += 1
                        last_frame_time = current_time
                        # Resetear contador de errores
                        error_count = 0
                        
                        # Mostrar estado periódicamente
                        if current_time - last_status_time > 30:
                            log("FFMPEG", "info", f"Reproduciendo: {err}")
                            last_status_time = current_time
                    
                    # Detectar errores
                    if 'error' in err.lower():
                        error_count += 1
                        
                        # Filtrar errores conocidos para no saturar logs
                        if 'decode_slice_header' in err or 'non-existing PPS' in err or 'no frame' in err:
                            # Estos son errores comunes de H.264, no son críticos a menos que sean muchos
                            if error_count % 20 == 0:
                                log("FFMPEG", "warning", f"Errores de decodificación H.264: {error_count}")
                        elif 'alsa' in err.lower():
                            # Error de audio ALSA, ignorable para seguir con video
                            log("FFMPEG", "warning", f"Error de audio ALSA detectado: {err}")
                        else:
                            log("FFMPEG", "error", f"Error FFmpeg: {err}")
                        
                        # Reiniciar si hay demasiados errores
                        if error_count > 30:  # Permitir más errores antes de reiniciar
                            log("FFMPEG", "error", f"Demasiados errores ({error_count}), reiniciando...")
                            break
                
                # Verificar timeout - si no recibimos frames por mucho tiempo
                if time.time() - last_frame_time > 15:  # Incrementar timeout a 15 segundos
                    error_count += 5
                    log("FFMPEG", "warning", "No se han recibido frames en 15 segundos")
                    last_frame_time = time.time()  # Resetear para evitar múltiples mensajes
                    
                    if error_count > 20:
                        log("FFMPEG", "error", "Timeout de frames, reiniciando proceso...")
                        break
                
                # Reducir uso de CPU
                time.sleep(0.1)
            
            # Cuando termina el proceso
            exit_code = self.ffmpeg_process.poll() if self.ffmpeg_process else None
            running_time = int(time.time() - start_time)
            log("FFMPEG", "info", f"Proceso FFmpeg terminado con código {exit_code} después de {running_time}s")
            
            # Capturar cualquier error de salida
            if exit_code != 0 and self.ffmpeg_process:
                try:
                    remaining_err = self.ffmpeg_process.stderr.read(1000)
                    if remaining_err:
                        log("FFMPEG", "error", f"Error de salida: {remaining_err.strip()}")
                except:
                    pass
            
            # Si el proceso duró poco tiempo, incrementar contador de fallos
            if running_time < 5:
                self.failed_attempts += 1
                log("FFMPEG", "warning", f"Intento fallido #{self.failed_attempts} (duración: {running_time}s)")
                
                # Incrementar tiempo de espera progresivamente
                wait_time = min(30, 5 * self.failed_attempts)
                log("FFMPEG", "info", f"Esperando {wait_time}s antes de reintentar...")
                time.sleep(wait_time)
            else:
                # Si funcionó por un tiempo razonable, resetear contador
                self.failed_attempts = 0
            
            # Limpiar y reiniciar
            if self.ffmpeg_process:
                try:
                    self.ffmpeg_process.terminate()
                    time.sleep(0.5)
                    if self.ffmpeg_process.poll() is None:
                        self.ffmpeg_process.kill()
                except:
                    pass
                self.ffmpeg_process = None
            
            # Reiniciar reproducción automáticamente
            log("FFMPEG", "info", "Reintentando reproducción...")
            self.stream_video()
        
        # Iniciar el monitoreo en un hilo separado
        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()

    def run(self):
        """Bucle principal de ejecución"""
        while True:
            try:
                # Iniciar la reproducción si no está en curso
                if not self.ffmpeg_process or (self.ffmpeg_process and self.ffmpeg_process.poll() is not None):
                    self.stream_video()
                
                # Verificar periódicamente el estado
                current_time = time.time()
                if current_time - self.last_config_check > CONFIG_CHECK_INTERVAL:
                    self.last_config_check = current_time
                    
                    # Comprobar si hay cambios en la URL o estado
                    log("SISTEMA", "info", "Verificando configuración...")
                    
                    # Si hay cambios, reiniciar la reproducción
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