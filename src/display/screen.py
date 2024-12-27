import subprocess
from config.settings import ASSETS_DIR

def show_default_image():
    try:
        default_image = ASSETS_DIR / 'default.png'
        ffmpeg_cmd = [
            'ffmpeg',
            '-loglevel', 'quiet',    # Silenciar logs
            '-i', str(default_image),
            '-vf', 'scale=1920:1080,format=rgb24',  # Forzar formato RGB
            '-pix_fmt', 'rgb565',
            '-f', 'fbdev',
            '-y',
            '/dev/fb0'
        ]
        subprocess.run(ffmpeg_cmd)
        
    except Exception as e:
        print(f'Error mostrando imagen: {e}') 