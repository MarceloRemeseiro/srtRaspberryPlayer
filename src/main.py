import time
import signal
from display.screen import show_default_image
from network.client import register_device, register_with_proxy, get_server_url
from stream.manager import StreamManager
from config.settings import DEVICE_ID

def main():
    stream_manager = StreamManager()

    def cleanup(signum, frame):
        stream_manager.stop_ffmpeg()
        show_default_image()
        exit(0)

    print(f"\nIniciando dispositivo {DEVICE_ID}")
    
    # Configurar manejo de señales
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    
    # Configuración inicial
    show_default_image()
    
    # Primero registrarse en el proxy
    print("\nRegistrando dispositivo en el servidor proxy...")
    register_with_proxy()
    
    # Luego intentar obtener la URL del servidor
    server_url = get_server_url(force_check=True)
    if server_url:
        print(f"Servidor asignado: {server_url}")
    else:
        print("No se ha asignado un servidor todavía. El dispositivo seguirá intentando.")
    
    # Registrar el dispositivo en el servidor si está disponible
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