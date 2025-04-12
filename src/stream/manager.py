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
        self.use_hw_decoder = self._check_hw_decoder()  # Verificar disponibilidad de decodificación HW
        
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

    def _check_hw_decoder(self):
        """Verificar si hay decodificadores de hardware disponibles"""
        try:
            # Verificar si V4L2 está disponible (para Raspberry Pi 5)
            v4l2_check = subprocess.run(
                ['ls', '/dev/video*'], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            
            if v4l2_check.returncode == 0 and v4l2_check.stdout:
                log("VIDEO", "success", "Dispositivos V4L2 detectados para decodificación HW")
                return True
                
            # Verificar si el codec MMAL está disponible (para Raspberry Pi 4 y anteriores)
            ffmpeg_check = subprocess.run(
                ['ffmpeg', '-encoders'], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            
            if 'h264_omx' in ffmpeg_check.stdout or 'h264_mmal' in ffmpeg_check.stdout:
                log("VIDEO", "success", "Codec MMAL/OMX detectado para decodificación HW")
                return True
                
            log("VIDEO", "warning", "No se detectó hardware de decodificación, usando decodificación por software")
            return False
        except Exception as e:
            log("VIDEO", "warning", f"Error verificando decodificadores HW: {e}")
            return False

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
                # Base del comando FFmpeg con configuración de red optimizada
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-loglevel', 'warning',
                    # Configuración de red y buffer
                    '-fflags', 'nobuffer+discardcorrupt',
                    '-flags', 'low_delay',
                    '-probesize', '32',
                    '-analyzeduration', '0',
                    # Configuración de SRT avanzada para reducir latencia
                    '-protocol_whitelist', 'file,udp,rtp,srt',
                    '-strict', 'experimental',
                ]
                
                # Añadir opciones de entrada
                ffmpeg_cmd.extend(['-i', srt_url])
                
                # Configuración de decodificación según disponibilidad de hardware
                if self.use_hw_decoder:
                    # Intentar usar decodificador de hardware V4L2 (Pi 5)
                    ffmpeg_cmd.extend([
                        '-c:v', 'h264_v4l2m2m',
                        '-threads', '4',          # Más threads para Pi 5
                    ])
                    log("FFMPEG", "info", "Usando decodificador de hardware V4L2")
                else:
                    # Configuración para decodificación por software
                    ffmpeg_cmd.extend([
                        '-threads', '2',
                    ])
                    log("FFMPEG", "info", "Usando decodificación por software")
                
                # Configuración de salida común
                ffmpeg_cmd.extend([
                    '-pix_fmt', 'rgb565',
                    '-f', 'fbdev',
                    '/dev/fb0'
                ])
                
                # Añadir audio usando ALSA si está disponible
                if self.has_audio:
                    ffmpeg_cmd.extend([
                        '-f', 'alsa',
                        '-ac', '2',
                        'sysdefault:CARD=vc4hdmi0'
                    ])
                    log("FFMPEG", "info", "Audio habilitado")
                else:
                    ffmpeg_cmd.append('-an')
                    log("FFMPEG", "warning", "Audio desactivado (no hay dispositivo disponible)")
                
                log("FFMPEG", "debug", f"Comando: {' '.join(ffmpeg_cmd)}")
                
                # Configurar buffer de lectura más grande para el proceso
                self.ffmpeg_process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    bufsize=10240  # Buffer más grande para mejor rendimiento
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
            
            while self.ffmpeg_process and self.ffmpeg_process.poll() is None:
                # Leer stderr (donde FFmpeg escribe sus logs)
                err = self.ffmpeg_process.stderr.readline()
                if err:
                    err = err.strip()
                    
                    # Solo mostrar logs críticos para evitar saturación
                    if 'error' in err.lower() and 'decode_slice_header' not in err:
                        log("FFMPEG", "error", err)
                    
                    # Mostrar info de frames periódicamente
                    if 'frame=' in err:
                        frame_count += 1
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
            
            # Cuando termine, reiniciar con un retraso
            if self.ffmpeg_process:
                # Limpiar el proceso terminado
                self.ffmpeg_process = None
                
                # Esperar un tiempo fijo antes de reintentar
                time.sleep(5)
                
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