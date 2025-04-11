import subprocess
from config.settings import ASSETS_DIR

def init_display():
    """Inicializa la pantalla"""
    # Por ahora solo un placeholder
    pass

def show_default_image():
    """Muestra la imagen por defecto"""
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