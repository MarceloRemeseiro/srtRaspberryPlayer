import time
import signal
from display.screen import show_default_image
from network.client import register_device, register_with_proxy, get_server_url, log
from stream.manager import StreamManager
from config.settings import DEVICE_ID

def main():
    stream_manager = StreamManager()

    def cleanup(signum, frame):
        log("SISTEMA", "info", "Deteniendo reproductor...")
        stream_manager.stop_ffmpeg()
        show_default_image()
        exit(0)

    log("SISTEMA", "info", f"=== Iniciando dispositivo {DEVICE_ID} ===")
    
    # Configurar manejo de señales
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    
    # Configuración inicial
    show_default_image()
    
    # Registro inicial
    log("SISTEMA", "info", "Iniciando proceso de registro...")
    register_with_proxy()
    
    # Obtener servidor asignado
    server_url = get_server_url(force_check=True)
    if server_url:
        log("SISTEMA", "success", f"Servidor asignado: {server_url}")
    else:
        log("SISTEMA", "info", "Sin servidor asignado. Esperando asignación...")
    
    # Registrar en servidor de streaming si está disponible
    register_device()
    
    log("SISTEMA", "info", "Iniciando bucle principal...")
    log("SISTEMA", "info", "=== Dispositivo listo ===")
    
    while True:
        try:
            stream_manager.stream_video()
        except Exception as e:
            log("SISTEMA", "error", f"Error en bucle principal: {e}")
        time.sleep(1)

if __name__ == '__main__':
    main() 