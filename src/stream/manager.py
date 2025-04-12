import time
import subprocess
import os
import signal
import threading
from config.settings import CONFIG_CHECK_INTERVAL
from display.screen import show_default_image
from network.client import get_srt_url, log

class StreamManager:
    def __init__(self):
        self.player_process = None
        self.last_config_check = time.time()
        self.last_srt_url = None
        # Limpieza inicial
        self._kill_existing_players()
        self._setup_audio()
        log("SISTEMA", "info", "StreamManager inicializado - Modo diagnóstico")

    def _kill_existing_players(self):
        """Mata cualquier proceso de reproducción existente"""
        try:
            subprocess.run(['pkill', '-9', 'mpv'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            subprocess.run(['pkill', '-9', 'vlc'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            subprocess.run(['pkill', '-9', 'cvlc'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            subprocess.run(['pkill', '-9', 'ffmpeg'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            time.sleep(1)
        except Exception as e:
            log("SISTEMA", "warning", f"Error matando procesos: {e}")

    def _setup_audio(self):
        """Configura el audio HDMI"""
        try:
            log("AUDIO", "info", "Configurando audio HDMI...")
            # Cargar módulo de sonido (puede ser necesario en algunos sistemas)
            subprocess.run(['modprobe', 'snd-bcm2835'], 
                         stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            
            # Configurar HDMI como salida
            subprocess.run(['amixer', 'cset', 'numid=3', '2'], 
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Establecer volumen
            subprocess.run(['amixer', 'set', 'Master', '100%'], 
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            log("AUDIO", "info", "Audio HDMI configurado")
        except Exception as e:
            log("AUDIO", "error", f"Error configurando audio: {e}")

    def stop_player(self):
        if self.player_process:
            try:
                self.player_process.terminate()
                time.sleep(0.5)
                if self.player_process.poll() is None:
                    self.player_process.kill()
            except Exception as e:
                log("PLAYER", "error", f"Error deteniendo reproductor: {e}")
            
            self.player_process = None
            self._kill_existing_players()

    def _monitor_process(self):
        """Monitorea el proceso para detectar problemas"""
        start_time = time.time()
        try:
            # Esperar a que termine el proceso
            exit_code = self.player_process.wait()
            runtime = time.time() - start_time
            log("DIAGNÓSTICO", "info", f"El reproductor terminó con código {exit_code} después de {int(runtime)} segundos")
            
            # Analizar si terminó cerca de los 2 minutos
            if 115 <= runtime <= 145:  # 2 minutos +/- 25 segundos
                log("DIAGNÓSTICO", "warning", "Patrón de terminación detectado cerca de los 2 minutos")
                # Intentar capturar más información sobre el sistema
                self._collect_system_info()

        except Exception as e:
            log("DIAGNÓSTICO", "error", f"Error en monitor: {e}")
        finally:
            # Reiniciar la reproducción si no hay un nuevo proceso ya iniciado
            if self.player_process is None or self.player_process.poll() is not None:
                self.stream_video()

    def _collect_system_info(self):
        """Recolecta información del sistema para diagnóstico"""
        try:
            log("DIAGNÓSTICO", "info", "Recolectando información del sistema...")
            
            # Verificar memoria disponible
            memory_info = subprocess.run(['free', '-m'], 
                                     stdout=subprocess.PIPE, 
                                     text=True).stdout
            log("DIAGNÓSTICO", "info", f"Información de memoria:\n{memory_info}")
            
            # Temperatura CPU
            try:
                temp_info = subprocess.run(['vcgencmd', 'measure_temp'], 
                                       stdout=subprocess.PIPE, 
                                       text=True).stdout
                log("DIAGNÓSTICO", "info", f"Temperatura: {temp_info}")
            except:
                log("DIAGNÓSTICO", "info", "No se pudo obtener temperatura")
            
            # Carga del sistema
            load_info = subprocess.run(['uptime'], 
                                   stdout=subprocess.PIPE, 
                                   text=True).stdout
            log("DIAGNÓSTICO", "info", f"Carga del sistema: {load_info}")
            
            # Problemas de red
            network_info = subprocess.run(['ping', '-c', '3', '8.8.8.8'], 
                                     stdout=subprocess.PIPE, 
                                     stderr=subprocess.PIPE,
                                     text=True)
            log("DIAGNÓSTICO", "info", f"Estado de red: {'OK' if network_info.returncode == 0 else 'Problemas'}")
            
        except Exception as e:
            log("DIAGNÓSTICO", "error", f"Error recolectando información: {e}")

    def stream_video(self):
        # Obtener la URL SRT del servidor
        srt_url = get_srt_url()
        if not srt_url:
            log("STREAM", "warning", "No hay URL SRT disponible. Reintentando...")
            show_default_image()
            return
        
        # Guardar la última URL SRT
        self.last_srt_url = srt_url
        
        # Si el reproductor no está corriendo, iniciarlo
        if not self.player_process or self.player_process.poll() is not None:
            log("STREAM", "info", f"Iniciando reproducción con SRT URL: {srt_url}")
            
            try:
                # Asegurar limpieza previa
                self._kill_existing_players()
                
                # Reconfigurar audio
                self._setup_audio()
                
                # Comando de MPV para diagnóstico
                mpv_cmd = [
                    'mpv',
                    srt_url,
                    '--fullscreen',
                    '--audio-device=alsa/sysdefault:CARD=vc4hdmi0',
                    '--volume=100',
                    '--msg-level=all=debug',            # Nivel de log alto para diagnóstico
                    '--log-file=/tmp/mpv-debug.log',    # Archivo de log para analizar después
                ]
                
                # Iniciar MPV con parámetros básicos para diagnóstico
                self.player_process = subprocess.Popen(
                    mpv_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                log("STREAM", "info", "Reproductor iniciado en modo diagnóstico")
                
                # Iniciar monitoreo en segundo plano
                monitor_thread = threading.Thread(
                    target=self._monitor_process,
                    daemon=True
                )
                monitor_thread.start()
                
            except Exception as e:
                log("STREAM", "error", f"Error iniciando reproducción: {e}")
                self.player_process = None

    def run(self):
        """Bucle principal de ejecución"""
        while True:
            try:
                # Iniciar la reproducción si no está en curso
                if not self.player_process or self.player_process.poll() is not None:
                    self.stream_video()
                
                # Verificar periódicamente cambios en la URL
                current_time = time.time()
                if current_time - self.last_config_check > CONFIG_CHECK_INTERVAL:
                    self.last_config_check = current_time
                    
                    new_srt_url = get_srt_url()
                    if new_srt_url and new_srt_url != self.last_srt_url:
                        log("SISTEMA", "info", "La URL SRT ha cambiado, reiniciando reproducción...")
                        self.stop_player()
                        time.sleep(1)
                        self.stream_video()
                
                # Dormir para no consumir CPU
                time.sleep(2)
                
            except Exception as e:
                log("SISTEMA", "error", f"Error en bucle principal: {e}")
                self._kill_existing_players()
                time.sleep(5) 