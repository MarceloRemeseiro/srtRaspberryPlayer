import time
import subprocess
import os
import signal
from config.settings import CONFIG_CHECK_INTERVAL
from display.screen import show_default_image
from network.client import get_srt_url, log

class StreamManager:
    def __init__(self):
        self.player_process = None
        self.last_config_check = time.time()
        self.last_srt_url = None
        # URL de prueba - para diagnosticar problema de congelación
        self.test_url = "srt://core.streamingpro.es:6000/?mode=caller&transtype=live&streamid=3a6f96cd-6400-4ecf-bdcd-ed23b792ad85,mode:request"
        # Limpieza inicial
        self._kill_existing_players()
        self._setup_audio()
        log("SISTEMA", "info", "StreamManager inicializado - Modo prueba directa")

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
            # Cargar módulo de sonido
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
                log("PLAYER", "info", "Deteniendo reproductor")
                self.player_process.terminate()
                time.sleep(0.5)
                if self.player_process.poll() is None:
                    log("PLAYER", "info", "Enviando SIGKILL al reproductor")
                    self.player_process.kill()
            except Exception as e:
                log("PLAYER", "error", f"Error deteniendo reproductor: {e}")
            
            self.player_process = None
            self._kill_existing_players()

    def start_direct_player(self, srt_url):
        """Inicia el reproductor MPV directamente como lo haces en consola"""
        log("PRUEBA", "info", f"Iniciando MPV directamente con URL: {srt_url}")
        
        try:
            # Comando exactamente igual al que funciona en consola
            mpv_cmd = [
                'mpv',
                srt_url,
                '--fullscreen',
                '--audio-device=alsa/sysdefault:CARD=vc4hdmi0',
                '--volume=100'
            ]
            
            # Ejecutar MPV como proceso hijo desacoplado
            process = subprocess.Popen(
                mpv_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setpgrp  # Desacoplar del proceso padre
            )
            
            log("PRUEBA", "info", f"MPV iniciado con PID: {process.pid}")
            return process
            
        except Exception as e:
            log("PRUEBA", "error", f"Error iniciando MPV: {e}")
            return None

    def stream_video(self):
        # Para pruebas, usar URL directa en lugar de obtenerla del servidor
        srt_url = self.test_url  # URL de prueba fija
        log("PRUEBA", "info", f"Usando URL de prueba: {srt_url}")
        
        # Si el reproductor no está corriendo, iniciarlo
        if not self.player_process or self.player_process.poll() is not None:
            try:
                # Asegurar limpieza previa
                self._kill_existing_players()
                
                # Reconfigurar audio
                self._setup_audio()
                
                # Iniciar reproductor directamente como en consola
                self.player_process = self.start_direct_player(srt_url)
                
                if not self.player_process:
                    log("STREAM", "error", "No se pudo iniciar el reproductor")
                    return
                
                # Registrar tiempo de inicio
                self.start_time = time.time()
                log("PRUEBA", "info", f"Reproductor iniciado a las {time.strftime('%H:%M:%S')}")
                
            except Exception as e:
                log("STREAM", "error", f"Error iniciando reproductor: {e}")
                self.player_process = None

    def run(self):
        """Bucle principal de ejecución simplificado para pruebas"""
        start_iteration = 0
        
        while True:
            try:
                # Iniciar la reproducción si no está en curso
                if not self.player_process or self.player_process.poll() is not None:
                    if self.player_process and self.player_process.poll() is not None:
                        runtime = time.time() - self.start_time
                        log("PRUEBA", "info", f"Reproductor terminó después de {int(runtime)} segundos con código: {self.player_process.poll()}")
                    
                    self.stream_video()
                    start_iteration += 1
                else:
                    # Verificar cuánto tiempo lleva ejecutándose
                    runtime = time.time() - self.start_time
                    if int(runtime) % 30 == 0:  # Registrar cada 30 segundos
                        log("PRUEBA", "info", f"Reproductor lleva {int(runtime)} segundos ejecutándose")
                
                # Dormir para no consumir CPU
                time.sleep(1)
                
            except Exception as e:
                log("SISTEMA", "error", f"Error en bucle principal: {e}")
                self._kill_existing_players()
                time.sleep(5) 