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
        """Verifica si hay dispositivos de audio disponibles mediante PulseAudio"""
        try:
            # Forzar el inicio de PulseAudio
            log("AUDIO", "info", "Verificando e iniciando PulseAudio...")
            
            # Matar cualquier instancia actual y reiniciar limpio
            try:
                subprocess.run(['pulseaudio', '--kill'], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE,
                              timeout=3)
                log("AUDIO", "info", "Instancia previa de PulseAudio terminada")
                time.sleep(1)
            except Exception:
                pass
                
            # Iniciar PulseAudio
            try:
                start_pulse = subprocess.run(['pulseaudio', '--start'], 
                                           stdout=subprocess.PIPE, 
                                           stderr=subprocess.PIPE,
                                           timeout=5)
                log("AUDIO", "info", "Comando para iniciar PulseAudio ejecutado")
                time.sleep(2)  # Dar tiempo a que se inicie completamente
            except Exception as e:
                log("AUDIO", "warning", f"Error iniciando PulseAudio: {e}")
            
            # Verificar si está funcionando
            try:
                pulse_check = subprocess.run(['pulseaudio', '--check'], 
                                           stdout=subprocess.PIPE, 
                                           stderr=subprocess.PIPE)
                
                if pulse_check.returncode == 0:
                    log("AUDIO", "success", "PulseAudio está funcionando")
                else:
                    log("AUDIO", "warning", "PulseAudio no está funcionando a pesar de los intentos")
            except Exception as e:
                log("AUDIO", "warning", f"Error verificando PulseAudio: {e}")
                
            # Configurar volumen al máximo
            try:
                subprocess.run(['amixer', 'set', 'Master', '100%'], check=False,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                log("AUDIO", "info", "Volumen configurado")
            except Exception as e:
                log("AUDIO", "warning", f"Error configurando volumen: {e}")
                
            # Verificar dispositivos de PulseAudio
            try:
                # Verificar los dispositivos de audio disponibles
                pulse_list = subprocess.run(['pactl', 'list', 'sinks', 'short'], 
                                           stdout=subprocess.PIPE, 
                                           stderr=subprocess.PIPE,
                                           text=True)
                
                if pulse_list.stdout:
                    log("AUDIO", "success", f"Dispositivos PulseAudio: {pulse_list.stdout.strip()}")
                    return True
                else:
                    log("AUDIO", "warning", "No se encontraron dispositivos PulseAudio")
            except Exception as e:
                log("AUDIO", "warning", f"Error listando dispositivos PulseAudio: {e}")
            
            # Si llegamos aquí, igual consideramos que hay audio y lo intentamos
            log("AUDIO", "info", "Asumiendo que hay audio disponible para intentar la reproducción")
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
        
        # URL SRT exacta que el usuario confirmó que funciona con su comando
        fixed_srt_url = "srt://core.streamingpro.es:6000/?mode=caller&transtype=live&streamid=7bb5ff4b-9470-4ff0-b5ff-16af476e8c1f,mode:request"
        
        # Si FFmpeg no está corriendo, iniciarlo
        if not self.ffmpeg_process or (self.ffmpeg_process and self.ffmpeg_process.poll() is not None):
            log("STREAM", "info", f"Iniciando reproducción con SRT URL probada")
            
            # Verificar que PulseAudio esté funcionando antes de iniciar FFmpeg
            try:
                # Lanzar --start antes de cada intento (es inofensivo si ya está corriendo)
                subprocess.run(['pulseaudio', '--start'], 
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                log("AUDIO", "info", "PulseAudio verificado antes de iniciar FFmpeg")
            except Exception as e:
                log("AUDIO", "warning", f"Error verificando PulseAudio: {e}")
            
            try:
                # Comando exacto que funciona, sin modificar una sola letra o parámetro
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-i', fixed_srt_url,
                    '-pix_fmt', 'rgb565',
                    '-f', 'fbdev',
                    '/dev/fb0'
                ]
                
                # Añadir audio usando PulseAudio si está disponible
                if self.has_audio:
                    ffmpeg_cmd.extend([
                        # Para añadir delay al audio (en lugar de adelantarlo)
                        '-itsoffset', '2.5',  # Retrasar el audio 2.5 segundos
                        '-i', fixed_srt_url,   # Duplicar la entrada para el audio
                        '-map', '0:v',         # Primera entrada: video
                        '-map', '1:a',         # Segunda entrada: audio
                        '-f', 'pulse',
                        'default'
                    ])
                    log("FFMPEG", "info", "Usando PulseAudio para salida de audio (con delay de 2.5s)")
                else:
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
            
            # Cuando termine, reiniciar con un retraso
            if self.ffmpeg_process:
                running_time = time.time() - start_time
                log("FFMPEG", "info", f"Proceso terminado después de {int(running_time)}s - Reiniciando...")
                
                # Limpiar el proceso terminado
                self.ffmpeg_process = None
                
                # Esperar antes de reiniciar
                time.sleep(3)
                
                # Reiniciar reproducción automáticamente
                self.stream_video()
                
        thread = threading.Thread(target=simple_monitor, daemon=True)
        thread.start() 