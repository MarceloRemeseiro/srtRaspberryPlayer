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
                # Configuración probada para SRT en Raspberry Pi
                # Comando básico para video
                ffmpeg_video_cmd = [
                    'ffmpeg',
                    # Nivel de log y configuración básica
                    '-loglevel', 'warning',
                    # Parámetros de sincronización temporal
                    '-async', '1',           # Sincronización automática de audio
                    '-vsync', '1',           # Mantener sincronización de video
                    # Entrada SRT
                    '-i', srt_url,
                    # Mapeado explícito de streams para asegurar orden correcto
                    '-map', '0:v:0',         # Video stream
                    '-pix_fmt', 'rgb565',
                    '-f', 'fbdev',
                    '/dev/fb0'
                ]
                
                # Comando básico para solo audio en un proceso separado
                ffmpeg_audio_cmd = [
                    'ffmpeg',
                    '-loglevel', 'warning',
                    # Sin retraso de inicio para el audio (-itsoffset -0.5 adelantaría el audio 0.5s)
                    '-i', srt_url,
                    '-vn',                   # Sin video
                    '-af', 'aresample=async=1000',  # Resampling de audio para mejor sincronización
                    '-f', 'alsa',
                    '-ac', '2',
                    'sysdefault:CARD=vc4hdmi0'
                ]
                
                # Primero intentar la reproducción con todo integrado (más eficiente)
                ffmpeg_cmd = ffmpeg_video_cmd.copy()
                # Añadir audio usando ALSA si está disponible
                if self.has_audio:
                    # En lugar de extend, insertamos al final pero antes de la salida de video
                    audio_params = [
                        '-map', '0:a:0',     # Audio stream
                        '-af', 'aresample=async=1000',  # Resampling de audio para mejor sincronización
                        '-f', 'alsa',
                        '-ac', '2',
                        'sysdefault:CARD=vc4hdmi0'
                    ]
                    
                    # Insertar parámetros de audio justo después de la entrada pero antes de la salida de video
                    ffmpeg_cmd = ffmpeg_cmd[:-5] + audio_params + ffmpeg_cmd[-5:]
                    log("FFMPEG", "info", "Audio habilitado con sincronización mejorada")
                else:
                    ffmpeg_cmd.append('-an')
                    log("FFMPEG", "warning", "Audio desactivado (no hay dispositivo disponible)")
                
                log("FFMPEG", "debug", f"Comando integrado: {' '.join(ffmpeg_cmd)}")
                
                # Registrar el tiempo de inicio para estadísticas
                self.last_ffmpeg_start = time.time()
                
                # Intentar primero con todo integrado
                self.ffmpeg_process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                
                # Verificar inmediatamente si se inició bien
                time.sleep(1)
                if self.ffmpeg_process.poll() is not None:
                    log("FFMPEG", "warning", "El modo integrado falló, intentando solo video...")
                    
                    # Si falló, intentar solo con video
                    self.ffmpeg_process = subprocess.Popen(
                        ffmpeg_video_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True
                    )
                    
                    # Verificar si el video solo funciona
                    time.sleep(1)
                    if self.ffmpeg_process.poll() is None:
                        log("FFMPEG", "success", "Video iniciado correctamente")
                        
                        # Si tenemos audio, iniciarlo en un proceso separado
                        if self.has_audio:
                            try:
                                # Iniciar un proceso separado para audio
                                log("FFMPEG", "info", "Iniciando audio separado...")
                                self.ffmpeg_audio_process = subprocess.Popen(
                                    ffmpeg_audio_cmd,
                                    stdout=subprocess.PIPE, 
                                    stderr=subprocess.PIPE,
                                    universal_newlines=True
                                )
                                log("FFMPEG", "success", "Audio iniciado en proceso separado")
                            except Exception as e:
                                log("FFMPEG", "error", f"Error iniciando audio: {e}")
                                self.ffmpeg_audio_process = None
                    else:
                        log("FFMPEG", "error", "No se pudo iniciar la reproducción de video")
                        self.ffmpeg_process = None
                        return
                else:
                    log("FFMPEG", "success", "Proceso integrado iniciado correctamente")
                
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
            error_count = 0  # Contador de errores consecutivos
            max_errors = 10  # Máximo de errores antes de reintentar
            
            while self.ffmpeg_process and self.ffmpeg_process.poll() is None:
                # Leer stderr (donde FFmpeg escribe sus logs)
                err = self.ffmpeg_process.stderr.readline()
                if err:
                    err = err.strip()
                    
                    # Solo mostrar logs críticos para evitar saturación
                    if 'error' in err.lower():
                        if 'decode_slice_header' not in err and 'Invalid data found' not in err:
                            # Errores importantes que no son de decodificación
                            log("FFMPEG", "error", err)
                        else:
                            # Errores de decodificación, incrementar contador
                            error_count += 1
                            
                            # Solo mostrar errores de decodificación ocasionalmente para no saturar logs
                            if error_count % 20 == 0:
                                log("FFMPEG", "warning", f"Errores de decodificación: {error_count}")
                                
                            # Si hay demasiados errores consecutivos, reiniciar
                            if error_count >= max_errors and time.time() - start_time > 15:  # Al menos 15s de intento
                                log("FFMPEG", "error", f"Demasiados errores de decodificación ({error_count}), reiniciando...")
                                break
                    
                    # Mostrar info de frames periódicamente
                    if 'frame=' in err:
                        frame_count += 1
                        error_count = 0  # Resetear contador de errores si recibimos frames
                        current_time = time.time()
                        if current_time - last_status_time > 30:  # Solo cada 30 segundos
                            log("FFMPEG", "info", f"Reproduciendo: {err}")
                            last_status_time = current_time
                
                # Dormir para reducir uso de CPU
                time.sleep(0.1)
            
            # Verificar el código de salida
            exit_code = self.ffmpeg_process.poll() if self.ffmpeg_process else None
            running_time = int(time.time() - start_time)
            log("FFMPEG", "info", f"Proceso terminado con código {exit_code} después de {running_time}s")
            
            # Si el proceso duró poco tiempo, incrementar contador de fallos
            if running_time < 5:
                self.failed_attempts += 1
                log("FFMPEG", "warning", f"Intento fallido #{self.failed_attempts} (duración: {running_time}s)")
                
                # Espera progresiva para evitar ciclos de reinicio rápido
                wait_time = min(30, 5 * self.failed_attempts)  # Máximo 30 segundos
                log("FFMPEG", "info", f"Esperando {wait_time}s antes de reintentar...")
                time.sleep(wait_time)
            else:
                # Si funcionó por un tiempo razonable, resetear contador
                self.failed_attempts = 0
            
            # Cuando termine, limpiar y reintentar
            if self.ffmpeg_process:
                self.ffmpeg_process = None
                
                # Reiniciar reproducción automáticamente
                log("FFMPEG", "info", "Reintentando reproducción...")
                self.stream_video()
                
        thread = threading.Thread(target=simple_monitor, daemon=True)
        thread.start()

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