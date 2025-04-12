import time
import subprocess
import threading
import os
import signal
from config.settings import CONFIG_CHECK_INTERVAL
from display.screen import show_default_image
from network.client import register_device, get_srt_url, log

class StreamManager:
    def __init__(self):
        self.player_process = None
        self.last_config_check = time.time()
        self.last_srt_url = None
        self.failed_attempts = 0
        self.last_output_time = time.time()  # Para monitoreo de congelación
        # Asegurar limpieza al iniciar
        self._kill_existing_players()
        self._setup_audio()
        log("SISTEMA", "info", "StreamManager inicializado - Usando MPV")

    def _kill_existing_players(self):
        """Mata cualquier proceso de reproducción existente"""
        try:
            log("SISTEMA", "info", "Matando procesos existentes...")
            # Matar cualquier proceso mpv
            subprocess.run(['pkill', '-9', 'mpv'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            # Matar cualquier proceso vlc/cvlc
            subprocess.run(['pkill', '-9', 'vlc'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            subprocess.run(['pkill', '-9', 'cvlc'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            # Matar cualquier proceso ffmpeg
            subprocess.run(['pkill', '-9', 'ffmpeg'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            time.sleep(1)
        except Exception as e:
            log("SISTEMA", "warning", f"Error matando procesos: {e}")

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
                # Enviar SIGTERM
                self.player_process.terminate()
                # Esperar a que termine
                for i in range(10):  # Esperar hasta 1 segundo
                    if self.player_process.poll() is not None:
                        break
                    time.sleep(0.1)
                
                # Si sigue vivo después de 1 segundo, enviar SIGKILL
                if self.player_process.poll() is None:
                    log("PLAYER", "warning", "El proceso no respondió a SIGTERM, enviando SIGKILL")
                    self.player_process.kill()
                    self.player_process.wait(timeout=1)
            except Exception as e:
                log("PLAYER", "error", f"Error deteniendo reproductor: {e}")
                try:
                    # Matar al proceso con SIGKILL
                    os.kill(self.player_process.pid, signal.SIGKILL)
                except:
                    pass
            
            self.player_process = None
            # Asegurar que todos los procesos relacionados estén muertos
            self._kill_existing_players()

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
                # Asegurar limpieza previa
                self._kill_existing_players()
                
                # Reconfigurar HDMI como salida 
                self._setup_audio()
                
                # Opciones para MPV con parámetros avanzados anti-congelación
                mpv_cmd = [
                    'mpv',                                         # Reproductor MPV
                    srt_url,                                       # URL SRT directa
                    '--fullscreen',                                # Pantalla completa
                    '--audio-device=alsa/sysdefault:CARD=vc4hdmi0',# Dispositivo de audio HDMI
                    '--volume=100',                                # Volumen al máximo
                    # Parámetros para prevenir congelaciones
                    '--cache=yes',                                 # Habilitar caché
                    '--cache-secs=5',                              # Caché de 5 segundos (aumentado)
                    '--network-timeout=5',                         # Timeout de red más corto
                    '--framedrop=decoder+vo',                      # Saltar frames agresivamente
                    '--video-sync=display-resample',               # Mejor sincronización de vídeo
                    '--untimed',                                   # Desactivar temporización estricta
                    '--keep-open=always',                          # Mantener abierto aunque haya errores
                    '--no-correct-pts',                            # Desactivar corrección de timestamps
                ]
                
                log("STREAM", "info", f"Iniciando MPV con parámetros avanzados anti-congelación")
                
                # Iniciar MPV
                self.player_process = subprocess.Popen(
                    mpv_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                # Monitoreo en hilo separado
                threading.Thread(
                    target=self._monitor_player,
                    daemon=True
                ).start()
                
                # Iniciar monitor de actividad para detectar congelación
                threading.Thread(
                    target=self._monitor_activity,
                    daemon=True
                ).start()
                
            except Exception as e:
                log("STREAM", "error", f"Error iniciando reproducción: {e}")
                self.player_process = None
    
    def _monitor_player(self):
        """Monitoreo simplificado para el proceso de reproducción"""
        start_time = time.time()
        
        try:
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
        except Exception as e:
            log("PLAYER", "error", f"Error en monitoreo: {e}")
        finally:
            # Asegurar que el proceso esté completamente terminado
            if self.player_process and self.player_process.poll() is None:
                try:
                    self.player_process.kill()
                except:
                    pass
            
            self.player_process = None
            # Limpiar procesos residuales
            self._kill_existing_players()
            # Continuar con reproducción
            self.stream_video()

    def _monitor_activity(self):
        """Monitor de actividad para detectar congelaciones graves y persistentes"""
        # Inicializar tiempo de inicio
        start_time = time.time()
        self.last_output_time = time.time()
        
        # Esperar 5 minutos antes de empezar a monitorear para dar tiempo a la reproducción
        time.sleep(300)
        
        # Contar reinicios para evitar bucles
        reinicios_totales = 0
        
        while self.player_process and self.player_process.poll() is None:
            try:
                # Verificar si el proceso sigue respondiendo cada 60 segundos
                time.sleep(60)
                
                if self.player_process and self.player_process.poll() is None:
                    # Proceso activo, actualizar tiempo de actividad
                    log("MONITOR", "info", "Reproducción activa, tiempo total: " + 
                        f"{int((time.time() - start_time) / 60)} minutos")
                    # Actualizar timestamp de salida para indicar que estamos verificando actividad
                    self.last_output_time = time.time()
                
                # Solo reiniciar si han pasado más de 10 minutos desde el último reinicio
                current_time = time.time()
                if reinicios_totales < 3 and current_time - self.last_output_time > 600:
                    log("MONITOR", "warning", "Posible congelación grave detectada. Reiniciando reproductor...")
                    # Reiniciar el reproductor
                    self.stop_player()
                    time.sleep(3)
                    self.stream_video()
                    reinicios_totales += 1
                    self.last_output_time = time.time()  # Actualizar timestamp después del reinicio
                    # Esperar 5 minutos antes de continuar monitoreando
                    time.sleep(300)
                    
            except Exception as e:
                log("MONITOR", "error", f"Error en monitoreo de actividad: {e}")
            
            # Dormir un poco antes del siguiente chequeo
            time.sleep(10)

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
                # Asegurar limpieza en caso de error
                self._kill_existing_players()
                time.sleep(10) 