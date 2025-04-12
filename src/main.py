import time
import signal
import subprocess
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
    
    # Configurar salida de audio HDMI mediante ALSA
    try:
        log("SISTEMA", "info", "Configurando audio HDMI mediante ALSA...")
        
        # Configurar audio para HDMI
        subprocess.run(['amixer', 'cset', 'numid=3', '2'], check=False, 
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log("SISTEMA", "info", "Salida configurada para HDMI")
        
        # Establecer volumen al máximo
        subprocess.run(['amixer', 'set', 'Master', '100%'], check=False,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log("SISTEMA", "info", "Volumen configurado al 100%")
        
        # Verificar dispositivos ALSA
        alsa_check = subprocess.run(['aplay', '-l'], 
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE,
                                 text=True)
        
        if "HDMI" in alsa_check.stdout:
            log("SISTEMA", "success", "Dispositivo HDMI ALSA detectado")
        else:
            log("SISTEMA", "warning", "No se detectó dispositivo HDMI en ALSA")
            
    except Exception as e:
        log("SISTEMA", "warning", f"Error configurando audio: {e}")
    
    # Configuración inicial
    show_default_image()
    
    log("SISTEMA", "info", "Iniciando reproducción simplificada...")
    
    # Iniciar reproducción una sola vez (con URL fija en stream_manager)
    stream_manager.stream_video()
    
    # Mantener el programa ejecutándose
    log("SISTEMA", "info", "Reproducción iniciada, manteniendo proceso activo...")
    
    try:
        # Bucle infinito para mantener el programa en ejecución
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        cleanup(None, None)

if __name__ == '__main__':
    main() 