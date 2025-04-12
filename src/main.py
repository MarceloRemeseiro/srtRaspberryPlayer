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
    
    # Configurar salida de audio HDMI y PulseAudio
    try:
        log("SISTEMA", "info", "Configurando audio...")
        
        # Forzar detener cualquier instancia existente de PulseAudio primero
        try:
            subprocess.run(['pulseaudio', '--kill'], 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE,
                          timeout=3)
            log("SISTEMA", "info", "Instancia previa de PulseAudio detenida")
            time.sleep(1)  # Esperar a que termine
        except Exception as e:
            log("SISTEMA", "info", f"No había instancia previa de PulseAudio: {str(e)}")
        
        # Iniciar PulseAudio con --start (siempre)
        log("SISTEMA", "info", "Iniciando PulseAudio...")
        subprocess.run(['pulseaudio', '--start'], 
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE,
                      timeout=5)
        
        # Dar tiempo a que inicie
        time.sleep(2)
        
        # Verificar que inició correctamente
        pulse_check = subprocess.run(['pulseaudio', '--check'], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE)
        
        if pulse_check.returncode == 0:
            log("SISTEMA", "success", "PulseAudio iniciado correctamente")
        else:
            log("SISTEMA", "warning", "No se pudo verificar PulseAudio, intentando de nuevo...")
            # Intentar una vez más
            subprocess.run(['pulseaudio', '--start', '--log-target=syslog'], 
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
        
        # Configurar audio para HDMI
        subprocess.run(['amixer', 'cset', 'numid=3', '2'], check=False, 
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Establecer volumen al máximo
        subprocess.run(['amixer', 'set', 'Master', '100%'], check=False,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
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