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
                # Configuración simple y directa para FFmpeg con audio
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-loglevel', 'warning',
                    '-stats',
                    # Parámetros SRT básicos
                    '-i', srt_url,
                    # Video
                    '-pix_fmt', 'rgb565',
                    '-f', 'fbdev',
                    '/dev/fb0'
                ]
                
                # Añadir audio si está disponible
                if self.has_audio:
                    ffmpeg_cmd.extend([
                        # Audio
                        '-f', 'alsa',
                        '-ac', '2',
                        'sysdefault:CARD=vc4hdmi0'
                    ])
                
                log("FFMPEG", "info", f"Comando: {' '.join(ffmpeg_cmd)}")
                
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
                    self._start_simple_monitor()
                else:
                    log("FFMPEG", "error", "El proceso FFmpeg falló al iniciar")
                    self.ffmpeg_process = None
            except Exception as e:
                log("FFMPEG", "error", f"Error iniciando proceso FFmpeg: {e}")
                self.ffmpeg_process = None
    
    def _start_simple_monitor(self):
        """Monitoreo simple para el proceso FFmpeg"""
        def monitor():
            start_time = time.time()
            
            # Esperar a que el proceso termine
            self.ffmpeg_process.wait()
            
            # Cuando termina, registrar información
            running_time = int(time.time() - start_time)
            exit_code = self.ffmpeg_process.returncode
            log("FFMPEG", "info", f"Proceso FFmpeg terminado con código {exit_code} después de {running_time}s")
            
            # Capturar errores si los hay
            if exit_code != 0:
                try:
                    stderr_output = self.ffmpeg_process.stderr.read()
                    if stderr_output:
                        log("FFMPEG", "error", f"Error de salida: {stderr_output[:500]}")
                except:
                    pass
            
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