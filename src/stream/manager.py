import time
import subprocess
import threading
from config.settings import CONFIG_CHECK_INTERVAL
from display.screen import show_default_image
from network.client import register_device, get_srt_url, log

class StreamManager:
    def __init__(self):
        self.ffmpeg_process = None
        self.last_config_check = time.time()
        self.last_srt_url = None

    def stop_ffmpeg(self):
        if self.ffmpeg_process:
            print('Deteniendo FFmpeg')
            self.ffmpeg_process.terminate()
            self.ffmpeg_process.wait()
            self.ffmpeg_process = None

    def stream_video(self):
        current_time = time.time()
        
        if current_time - self.last_config_check > CONFIG_CHECK_INTERVAL:
            print(f"\n[STREAM] Verificando configuración después de {CONFIG_CHECK_INTERVAL} segundos")
            srt_url = get_srt_url()
            self.last_config_check = current_time
            
            if srt_url:
                if srt_url != self.last_srt_url:
                    print(f"[STREAM] ⚡ Nueva URL detectada")
                    self.last_srt_url = srt_url
                    if self.ffmpeg_process:
                        self.stop_ffmpeg()
            else:
                self.last_srt_url = None
                self.stop_ffmpeg()
                show_default_image()
                register_device('NO REPRODUCIENDO')
                print("[STATUS] ❌ No hay SRT configurado")
                return
        
        srt_url = self.last_srt_url
        
        if not srt_url:
            show_default_image()
            register_device('NO REPRODUCIENDO')
            print("[STATUS] ❌ No hay URL configurada")
            time.sleep(CONFIG_CHECK_INTERVAL)
            return
        
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            return
            
        print(f"\n[STREAM] 🎬 Iniciando reproducción: {srt_url}")
        
        self._start_ffmpeg(srt_url)

    def _start_ffmpeg(self, srt_url):
        """Inicia el proceso FFmpeg con la URL dada"""
        try:
            log("STREAM", "info", f"Iniciando reproducción SRT: {srt_url}")
            
            ffmpeg_cmd = [
                'ffmpeg',
                '-loglevel', 'debug',        # Cambiado a debug para ver más detalles
                '-fflags', 'nobuffer',
                '-flags', 'low_delay',
                '-i', srt_url,
                '-vf', 'scale=1920:1080',
                '-pix_fmt', 'rgb565',
                '-f', 'fbdev',
                '-y', '/dev/fb0',
                '-f', 'alsa',
                '-ac', '2',
                '-ar', '48000',
                'default'
            ]
            
            log("FFMPEG", "info", f"Comando completo: {' '.join(ffmpeg_cmd)}")
            
            # Ejecutar FFmpeg y capturar la salida inmediatamente
            self.ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )
            
            # Verificar si FFmpeg inició correctamente
            time.sleep(2)  # Esperar un momento para ver si hay errores iniciales
            if self.ffmpeg_process.poll() is not None:
                # FFmpeg terminó inmediatamente, algo salió mal
                out, err = self.ffmpeg_process.communicate()
                log("FFMPEG", "error", f"FFmpeg falló al iniciar. Código: {self.ffmpeg_process.returncode}")
                log("FFMPEG", "error", f"Error: {err}")
                log("FFMPEG", "error", f"Salida: {out}")
                raise Exception("FFmpeg falló al iniciar")
            
            log("FFMPEG", "success", "FFmpeg iniciado correctamente")
            register_device('REPRODUCIENDO')
            
            # Iniciar monitoreo de salida
            self._start_output_monitor()
            
        except Exception as e:
            log("FFMPEG", "error", f"Error iniciando FFmpeg: {str(e)}")
            show_default_image()
            register_device('NO REPRODUCIENDO')
            self.ffmpeg_process = None
            raise

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