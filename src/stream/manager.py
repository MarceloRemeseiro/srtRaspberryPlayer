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
        self.has_audio = self._check_audio_device()

    def _check_audio_device(self):
        """Verifica si hay dispositivos de audio disponibles"""
        try:
            # Comprobar si existe /dev/snd
            if not os.path.exists('/dev/snd'):
                log("AUDIO", "warning", "No se encontró /dev/snd")
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
            log("AUDIO", "info", "Dispositivos de audio encontrados")
            return True
            
        except Exception as e:
            log("AUDIO", "error", f"Error verificando dispositivos de audio: {e}")
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
        
        if current_time - self.last_config_check > CONFIG_CHECK_INTERVAL:
            log("STREAM", "info", f"Verificando configuración después de {CONFIG_CHECK_INTERVAL} segundos")
            srt_url = get_srt_url()
            self.last_config_check = current_time
            
            # Si hay una nueva URL SRT
            if srt_url:
                log("STREAM", "info", f"URL SRT disponible: {srt_url}")
                if srt_url != self.last_srt_url:
                    log("STREAM", "info", "Nueva URL SRT detectada, reiniciando reproducción")
                    self.stop_ffmpeg()
                    self.last_srt_url = srt_url
            else:
                # Si no hay URL, detener reproducción
                if self.ffmpeg_process:
                    log("STREAM", "info", "No hay URL SRT, deteniendo reproducción")
                    self.stop_ffmpeg()
                self.last_srt_url = None
                show_default_image()
                register_device('NO REPRODUCIENDO')
                return
        
        # Si tenemos URL SRT pero ffmpeg no está corriendo, iniciarlo
        # Añadir protección para evitar reinicios frecuentes
        if (self.last_srt_url and 
            (not self.ffmpeg_process or 
             (self.ffmpeg_process and self.ffmpeg_process.poll() is not None)) and
            (current_time - self.last_ffmpeg_start > 5)):  # Esperar al menos 5 segundos entre reinicios
            
            log("STREAM", "info", f"Iniciando reproducción con URL: {self.last_srt_url}")
            try:
                # Actualizar timestamp antes de iniciar
                self.last_ffmpeg_start = current_time
                
                # Configuración base de FFmpeg
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-loglevel', 'info',
                    '-fflags', 'nobuffer+discardcorrupt+genpts',  # Ignorar datos corruptos y generar timestamps
                    '-flags', 'low_delay',
                    '-probesize', '1M',                  # Aumentar tamaño de análisis
                    '-analyzeduration', '2000000',       # Aumentar duración de análisis
                    '-protocol_whitelist', 'file,udp,rtp,srt', # Protocolos permitidos
                    '-skip_frame', 'noref',              # Saltar frames no referenciales
                    '-re',                               # Leer a velocidad nativa
                    '-stimeout', '5000000',              # Timeout SRT (5 segundos)
                    '-i', self.last_srt_url,
                    '-vf', 'scale=1920:1080',
                    '-pix_fmt', 'rgb565',
                    '-f', 'fbdev',
                    '-y', '/dev/fb0'
                ]
                
                # Añadir audio solo si está disponible
                if not self.has_audio:
                    ffmpeg_cmd.append('-an')  # Desactivar audio
                    log("FFMPEG", "warning", "Reproduciendo sin audio (no hay dispositivo disponible)")
                else:
                    ffmpeg_cmd.extend([
                        '-f', 'alsa',
                        '-ac', '2',
                        '-ar', '48000',
                        'default'
                    ])
                    log("FFMPEG", "info", "Reproduciendo con audio")
                
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

    def _start_output_monitor(self):
        """Monitorea la salida de FFmpeg en tiempo real"""
        def monitor():
            while self.ffmpeg_process and self.ffmpeg_process.poll() is None:
                # Leer stderr (donde FFmpeg escribe sus logs)
                err = self.ffmpeg_process.stderr.readline()
                if err:
                    err = err.strip()
                    if 'Connection refused' in err or 'Connection timed out' in err:
                        log("FFMPEG", "error", f"Error de conexión SRT: {err}")
                    elif 'Error' in err or 'error' in err:
                        log("FFMPEG", "error", f"Error FFmpeg: {err}")
                    elif 'Opening' in err or 'Stream mapping' in err:
                        log("FFMPEG", "info", err)
                    else:
                        log("FFMPEG", "debug", err)

                # Verificar si FFmpeg sigue vivo
                if self.ffmpeg_process.poll() is not None:
                    log("FFMPEG", "error", f"FFmpeg terminó con código: {self.ffmpeg_process.returncode}")
                    break

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start() 