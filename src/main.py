import time
import signal
from display.screen import show_default_image
from network.client import register_device
from stream.manager import StreamManager
from config.settings import DEVICE_ID, SERVER_URL

def main():
    stream_manager = StreamManager()

    def cleanup(signum, frame):
        stream_manager.stop_ffmpeg()
        show_default_image()
        exit(0)

    print(f"\nIniciando dispositivo {DEVICE_ID}")
    print(f"Servidor: {SERVER_URL}")
    
    # Configurar manejo de señales
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    
    # Configuración inicial
    show_default_image()
    register_device()
    
    print("\nIniciando bucle principal...")
    while True:
        try:
            stream_manager.stream_video()
        except Exception as e:
            print(f'Error en main loop: {e}')
        time.sleep(1)

if __name__ == '__main__':
    main() 