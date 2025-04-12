import time
import subprocess
import threading
import os
from config.settings import CONFIG_CHECK_INTERVAL
from display.screen import show_default_image
from network.client import register_device, get_srt_url, log

class StreamManager:
    def __init__(self):
        self.player_process = None
        self.last_config_check = time.time()
        self.last_srt_url = None
        self.failed_attempts = 0
        self._setup_audio()
        log("SISTEMA", "info", "StreamManager inicializado - Usando VLC")

    def _setup_audio(self):
        """Configura el audio HDMI"""
        try:
            log("AUDIO", "info", "Configurando audio HDMI...")
            
            # Configurar HDMI como salida principal
            subprocess.run(['amixer', 'cset', 'numid=3', '2'], 
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            log("AUDIO", "info", "HDMI configurado como salida principal")
            
            # Establecer volumen al máximo
            subprocess.run(['amixer', 'set', 'Master', '100%'], 
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            log("AUDIO", "info", "Volumen configurado al máximo")
            
        except Exception as e:
            log("AUDIO", "error", f"Error configurando audio: {e}")

    def stop_player(self):
        if self.player_process:
            log("PLAYER", "info", "Deteniendo reproductor")
            try:
                self.player_process.terminate()
                self.player_process.wait(timeout=3)
            except Exception as e:
                log("PLAYER", "error", f"Error deteniendo reproductor: {e}")
                try:
                    self.player_process.kill()
                except:
                    pass
            self.player_process = None

    def stream_video(self):
        # Obtener la URL SRT del servidor
        srt_url = get_srt_url()
        if not srt_url:
            log("STREAM", "warning", "No hay URL SRT disponible. Reintentando en 10 segundos...")
            show_default_image()
            time.sleep(10)
            return
        
        # Guardar la última URL SRT para reutilizarla en caso de reconexión
        self.last_srt_url = srt_url
        
        # Si el reproductor no está corriendo, iniciarlo
        if not self.player_process or (self.player_process and self.player_process.poll() is not None):
            log("STREAM", "info", f"Iniciando reproducción con SRT URL: {srt_url}")
            
            try:
                # Reconfigurar HDMI como salida 
                self._setup_audio()
                
                # Opciones para VLC con decodificación hardware y sincronización
                vlc_cmd = [
                    'cvlc',  # VLC sin interfaz
                    '-vvv',  # Modo verboso para mejor diagnóstico
                    srt_url,
                    # Habilitar decodificación por hardware
                    '--avcodec-hw=any',  # Usar cualquier aceleración hardware disponible
                    '--codec=h264',      # Forzar codec h264
                    # Ajustes para sincronización audio/video
                    '--audio-desync=500',   # Ajuste fino de sincronización (500ms adelanto en audio)
                    '--no-audio-time-stretch', # Desactivar estiramiento de tiempo en audio
                    # Configuración de caché para streaming
                    '--network-caching=500',  # Menos caché para reducir latencia
                    '--live-caching=300',     # Caché para contenido en vivo
                    # Salida de video y audio
                    '--mmal-display-x=0',    # Parámetros de posición en pantalla
                    '--mmal-display-y=0',
                    '--mmal-display-width=0',
                    '--mmal-display-height=0',
                    '--fullscreen',
                    '--aout=alsa',           # Salida de audio ALSA
                    '--gain=1.0'             # Ganancia normal
                ]
                
                log("STREAM", "info", f"Iniciando VLC con aceleración hardware y sincronización mejorada")
                
                # Iniciar VLC
                self.player_process = subprocess.Popen(
                    vlc_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                # Monitoreo en hilo separado
                threading.Thread(
                    target=self._monitor_player,
                    daemon=True
                ).start()
                
            except Exception as e:
                log("STREAM", "error", f"Error iniciando reproducción con VLC: {e}")
                self.player_process = None
    
    def _monitor_player(self):
        """Monitoreo simplificado para el proceso de reproducción"""
        start_time = time.time()
        
        # Esperar a que el proceso termine
        exit_code = self.player_process.wait()
        
        # Procesar resultado
        running_time = int(time.time() - start_time)
        log("PLAYER", "info", f"Reproductor terminado con código {exit_code} después de {running_time}s")
        
        # Reintentar con espera progresiva si falló rápidamente
        if running_time < 5:
            self.failed_attempts += 1
            wait_time = min(30, 5 * self.failed_attempts)
            log("PLAYER", "info", f"Intento fallido #{self.failed_attempts}, esperando {wait_time}s antes de reintentar")
            time.sleep(wait_time)
        else:
            self.failed_attempts = 0
        
        # Limpiar y reiniciar
        self.player_process = None
        self.stream_video()

    def run(self):
        """Bucle principal de ejecución"""
        while True:
            try:
                # Iniciar la reproducción si no está en curso
                if not self.player_process or (self.player_process and self.player_process.poll() is not None):
                    self.stream_video()
                
                # Verificar periódicamente cambios en la URL
                current_time = time.time()
                if current_time - self.last_config_check > CONFIG_CHECK_INTERVAL:
                    self.last_config_check = current_time
                    
                    new_srt_url = get_srt_url()
                    if new_srt_url != self.last_srt_url:
                        log("SISTEMA", "info", "La URL SRT ha cambiado, reiniciando reproducción...")
                        self.stop_player()
                        time.sleep(1)
                        self.stream_video()
                
                # Dormir para no consumir CPU
                time.sleep(5)
                
            except Exception as e:
                log("SISTEMA", "error", f"Error en bucle principal: {e}")
                time.sleep(10) 