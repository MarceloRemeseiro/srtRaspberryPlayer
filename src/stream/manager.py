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
                # Configuración optimizada para SRT basada en la documentación de FFmpeg
                log("FFMPEG", "info", "Configurando parámetros optimizados para SRT")
                
                # Parámetros base para todos los modos (con o sin audio)
                base_params = [
                    'ffmpeg',
                    # Nivel de logs para diagnóstico
                    '-loglevel', 'warning',
                    # Incluir estadísticas
                    '-stats',
                    # Parámetros de buffer y rendimiento
                    '-rtbufsize', '16M',    # Buffer más grande para estabilidad
                    '-rw_timeout', '5000000',  # 5 segundos de timeout de lectura
                    # Parámetros para sincronización
                    '-async', '1',           # Sincronización automática de audio
                    '-vsync', '1',           # Mantener sincronización de video constante
                    # Entrada SRT
                    '-i', srt_url,
                ]
                
                # Selección de output streams (mapeado explícito para control ordenado)
                output_params = []
                
                # Configurar salida de video siempre
                video_params = [
                    # Seleccionar stream de video
                    '-map', '0:v:0',
                    # Configuración de salida de video
                    '-pix_fmt', 'rgb565',
                    '-f', 'fbdev',
                    '/dev/fb0'
                ]
                
                # Configurar salida de audio si está disponible
                if self.has_audio:
                    audio_params = [
                        # Seleccionar stream de audio
                        '-map', '0:a:0',
                        # Resampling adaptativo para mejor sincronización
                        '-af', 'aresample=async=1000',
                        # Configuración de salida de audio
                        '-f', 'alsa',
                        '-ac', '2',     # Estéreo
                        'sysdefault:CARD=vc4hdmi0'       # Dispositivo estándar ALSA
                    ]
                    log("FFMPEG", "info", "Audio habilitado con sincronización mejorada")
                    
                    # Construir comando completo con audio
                    ffmpeg_cmd = base_params + video_params + audio_params
                else:
                    # Sin audio
                    log("FFMPEG", "warning", "Audio desactivado (no hay dispositivo disponible)")
                    ffmpeg_cmd = base_params + ['-an'] + video_params
                
                # Registrar comando para diagnóstico
                log("FFMPEG", "debug", f"Comando: {' '.join(ffmpeg_cmd)}")
                
                # Iniciar el proceso FFmpeg
                self.last_ffmpeg_start = time.time()
                self.ffmpeg_process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                
                # Verificar si se inició correctamente
                time.sleep(1)
                if self.ffmpeg_process.poll() is None:
                    log("FFMPEG", "success", "Proceso FFmpeg iniciado correctamente")
                    
                    # Si el primer intento fue exitoso, iniciar monitoreo
                    self._start_enhanced_monitor()
                else:
                    # Si falló, intentar con una configuración alternativa
                    log("FFMPEG", "warning", "La configuración inicial falló, probando configuración alternativa...")
                    
                    # Opción alternativa: usar FFmpeg con menos opciones
                    alt_cmd = [
                        'ffmpeg',
                        '-loglevel', 'warning',
                        '-i', srt_url
                    ]
                    
                    # Agregar salida de video
                    alt_cmd.extend([
                        '-pix_fmt', 'rgb565',
                        '-f', 'fbdev',
                        '/dev/fb0'
                    ])
                    
                    # Agregar salida de audio si está disponible
                    if self.has_audio:
                        alt_cmd.extend([
                            '-f', 'alsa',
                            '-ac', '2',
                            'default'
                        ])
                    else:
                        alt_cmd.append('-an')
                    
                    log("FFMPEG", "info", f"Comando alternativo: {' '.join(alt_cmd)}")
                    
                    # Iniciar proceso alternativo
                    self.ffmpeg_process = subprocess.Popen(
                        alt_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True
                    )
                    
                    # Verificar si se inició correctamente
                    time.sleep(1)
                    if self.ffmpeg_process.poll() is None:
                        log("FFMPEG", "success", "Proceso alternativo iniciado correctamente")
                        self._start_enhanced_monitor()
                    else:
                        # Capturar errores para diagnóstico
                        log("FFMPEG", "error", "Ambos intentos fallaron")
                        if self.ffmpeg_process:
                            try:
                                error_output = self.ffmpeg_process.stderr.read()
                                log("FFMPEG", "error", f"Error FFmpeg: {error_output[:500]}...")
                            except Exception as e:
                                log("FFMPEG", "error", f"Error leyendo stderr: {e}")
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
                        if 'decode_slice_header' in err or 'Invalid data found' in err:
                            if error_count % 20 == 0:
                                log("FFMPEG", "warning", f"Errores de decodificación: {error_count}")
                        else:
                            log("FFMPEG", "error", f"Error FFmpeg: {err}")
                        
                        # Reiniciar si hay demasiados errores
                        if error_count > 20:
                            log("FFMPEG", "error", f"Demasiados errores ({error_count}), reiniciando...")
                            break
                
                # Verificar timeout - si no recibimos frames por mucho tiempo
                if time.time() - last_frame_time > 10:
                    error_count += 5
                    log("FFMPEG", "warning", "No se han recibido frames en 10 segundos")
                    last_frame_time = time.time()  # Resetear para evitar múltiples mensajes
                    
                    if error_count > 15:
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