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
                
                # Opciones para VLC
                vlc_cmd = [
                    'cvlc',  # VLC sin interfaz
                    '--no-video-title-show',
                    '--fullscreen',
                    '--quiet',
                    '--no-loop',
                    '--no-repeat',
                    '--play-and-exit',
                    # Configuración de audio mejorada
                    '--aout=alsa',
                    '--alsa-audio-device=default',  # Usar el dispositivo de audio por defecto
                    '--gain=1.0',  # Ganancia de audio normal
                    '--audio-filter=compressor',  # Mejor procesamiento de audio
                    # Configuración de video
                    '--vout=mmal_vout',  # Salida de video optimizada para Raspberry Pi
                    '--video-on-top',
                    # Configuración de red y caché
                    '--live-caching=300',  # Valor más bajo para streaming en vivo
                    '--network-caching=1000',  # Búfer de red (ms)
                    '--clock-jitter=0',  # Reduce jitter en la sincronización
                    '--clock-synchro=0',  # Desactiva la sincronización de reloj para SRT
                    '--sout-mux-caching=300',
                    # Protocolo SRT con comillas para evitar problemas de shell
                    f'"{srt_url}"'
                ]
                
                log("STREAM", "info", f"Iniciando VLC con configuración mejorada")
                
                # Iniciar VLC con shell=True para manejar la URL SRT correctamente
                self.player_process = subprocess.Popen(
                    ' '.join(vlc_cmd),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=True
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