import time
import subprocess
from config.settings import CONFIG_CHECK_INTERVAL
from display.screen import show_default_image
from network.client import register_device, get_srt_url

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
        
        ffmpeg_cmd = [
            'ffmpeg',
            '-loglevel', 'warning',
            '-fflags', 'nobuffer',
            '-flags', 'low_delay',
            '-i', srt_url,
            '-vf', 'scale=1920:1080',
            '-pix_fmt', 'rgb565',
            '-f', 'fbdev',
            '-y',
            '/dev/fb0'
        ]
        
        try:
            self.ffmpeg_process = subprocess.Popen(ffmpeg_cmd, stderr=subprocess.PIPE)
            register_device('ONLINE')
            print("[STATUS] ✓ Iniciado - ONLINE")
            
        except Exception as e:
            show_default_image()
            register_device('NO REPRODUCIENDO')
            print("[STATUS] ❌ Error iniciando stream") 