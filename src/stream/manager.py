import time
import subprocess
import os
import signal
import tempfile
import threading
from config.settings import CONFIG_CHECK_INTERVAL
from display.screen import show_default_image
from network.client import get_srt_url, log

class StreamManager:
    def __init__(self):
        self.player_process = None
        self.last_config_check = time.time()
        self.last_srt_url = None
        self.auto_restart_timer = None
        # URL de prueba - para diagnosticar problema de congelación
        self.test_url = "srt://core.streamingpro.es:6000/?mode=caller&transtype=live&streamid=3a6f96cd-6400-4ecf-bdcd-ed23b792ad85,mode:request"
        self.script_path = None
        # Limpieza inicial
        self._kill_existing_players()
        self._setup_audio()
        # Tiempo en segundos antes de reiniciar automáticamente (justo antes de la congelación)
        self.auto_restart_seconds = 110  # Reiniciar cada 1m 50s
        log("SISTEMA", "info", "StreamManager inicializado - Modo auto-reinicio preventivo")

    def _kill_existing_players(self):
        """Mata cualquier proceso de reproducción existente"""
        try:
            subprocess.run(['pkill', '-9', 'mpv'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            subprocess.run(['pkill', '-9', 'vlc'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            subprocess.run(['pkill', '-9', 'cvlc'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            subprocess.run(['pkill', '-9', 'ffmpeg'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            # Terminar cualquier script shell activo
            if self.script_path and os.path.exists(self.script_path):
                try:
                    os.remove(self.script_path)
                except:
                    pass
            
            # Cancelar el temporizador si existe
            if self.auto_restart_timer:
                self.auto_restart_timer.cancel()
                self.auto_restart_timer = None
                
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
        log("PLAYER", "info", "Deteniendo reproductor")
        
        if self.player_process:
            try:
                self.player_process.terminate()
                time.sleep(0.5)
                if self.player_process.poll() is None:
                    log("PLAYER", "info", "Enviando SIGKILL al reproductor")
                    self.player_process.kill()
            except Exception as e:
                log("PLAYER", "error", f"Error deteniendo reproductor: {e}")
            
            self.player_process = None
        
        # Cancelar el temporizador si existe
        if self.auto_restart_timer:
            self.auto_restart_timer.cancel()
            self.auto_restart_timer = None
        
        # Matar todos los procesos MPV restantes
        self._kill_existing_players()

    def _auto_restart(self):
        """Realiza un reinicio automático preventivo"""
        log("AUTO", "info", f"Ejecutando reinicio preventivo automático después de {self.auto_restart_seconds} segundos")
        
        # Detener el reproductor actual
        self.stop_player()
        
        # Pequeña pausa para que los procesos terminen por completo
        time.sleep(2)
        
        # Iniciar el reproductor de nuevo
        self.stream_video()

    def start_via_shell_script(self, srt_url):
        """Inicia el reproductor a través de un script shell independiente"""
        log("SHELL", "info", f"Iniciando MPV a través de shell con URL: {srt_url}")
        
        try:
            # Crear un script shell temporal
            fd, script_path = tempfile.mkstemp(suffix='.sh')
            self.script_path = script_path
            
            with os.fdopen(fd, 'w') as f:
                f.write('#!/bin/bash\n\n')
                f.write('# Script generado automáticamente para MPV\n')
                f.write(f'# Fecha: {time.strftime("%Y-%m-%d %H:%M:%S")}\n\n')
                
                # El comando exacto que funciona desde consola
                f.write(f'mpv "{srt_url}" --fullscreen --audio-device=alsa/sysdefault:CARD=vc4hdmi0 --volume=100\n')
                
                # Añadir código para eliminar el script después de ejecutarse
                f.write('\n# Eliminar este script al terminar\n')
                f.write(f'rm -f "{script_path}"\n')
            
            # Hacer el script ejecutable
            os.chmod(script_path, 0o755)
            
            # Ejecutar el script en segundo plano
            log("SHELL", "info", f"Ejecutando script: {script_path}")
            process = subprocess.Popen(
                ['/bin/bash', script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # Desconectar completamente del proceso principal
                start_new_session=True
            )
            
            log("SHELL", "info", f"Script iniciado con PID: {process.pid}")
            return process
            
        except Exception as e:
            log("SHELL", "error", f"Error creando/ejecutando script: {e}")
            if self.script_path and os.path.exists(self.script_path):
                try:
                    os.remove(self.script_path)
                except:
                    pass
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
                
                # Iniciar MPV mediante script shell independiente
                log("PRUEBA", "info", "Iniciando MPV mediante script shell independiente")
                self.player_process = self.start_via_shell_script(srt_url)
                
                if not self.player_process:
                    log("STREAM", "error", "No se pudo iniciar el reproductor")
                    return
                
                # Registrar tiempo de inicio
                self.start_time = time.time()
                log("PRUEBA", "info", f"Script iniciado a las {time.strftime('%H:%M:%S')}")
                
                # Programar reinicio automático preventivo
                self.auto_restart_timer = threading.Timer(self.auto_restart_seconds, self._auto_restart)
                self.auto_restart_timer.daemon = True
                self.auto_restart_timer.start()
                log("AUTO", "info", f"Programado reinicio automático en {self.auto_restart_seconds} segundos")
                
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
                        log("PRUEBA", "info", f"Proceso terminado después de {int(runtime)} segundos con código: {self.player_process.poll()}")
                    
                    self.stream_video()
                    start_iteration += 1
                else:
                    # Verificar cuánto tiempo lleva ejecutándose
                    runtime = time.time() - self.start_time
                    if int(runtime) % 30 == 0:  # Registrar cada 30 segundos
                        log("PRUEBA", "info", f"Proceso lleva {int(runtime)} segundos ejecutándose")
                        
                        # Verificar si MPV sigue ejecutándose
                        mpv_check = subprocess.run(
                            "pgrep mpv", 
                            shell=True, 
                            stdout=subprocess.PIPE, 
                            stderr=subprocess.PIPE
                        )
                        
                        if mpv_check.returncode != 0:
                            log("PRUEBA", "warning", "No se encontró proceso MPV a pesar de que el script sigue ejecutándose")
                            # Forzar reinicio
                            self.stop_player()
                            self.stream_video()
                
                # Dormir para no consumir CPU
                time.sleep(1)
                
            except Exception as e:
                log("SISTEMA", "error", f"Error en bucle principal: {e}")
                self._kill_existing_players()
                time.sleep(5) 