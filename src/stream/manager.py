import time
import subprocess
import os
import signal
import tempfile
import threading
import shutil
from datetime import datetime
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
        
        # Configuración para diagnóstico
        self.debug_dir = "/home/pi/srt-player-debug"
        self.create_debug_dir()
        
        # Limpieza inicial
        self._kill_existing_players()
        self._setup_audio()
        
        # Tiempo en segundos antes de reiniciar automáticamente (justo antes de la congelación)
        self.auto_restart_seconds = 110  # Reiniciar cada 1m 50s
        
        # Variables para datos de diagnóstico
        self.session_start = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = os.path.join(self.debug_dir, f"session_{self.session_start}")
        os.makedirs(self.session_dir, exist_ok=True)
        
        # Iniciar captura de información del sistema
        self.start_system_monitoring()
        
        log("SISTEMA", "info", f"StreamManager inicializado - Modo diagnóstico avanzado (sesión: {self.session_start})")

    def create_debug_dir(self):
        """Crea el directorio para archivos de diagnóstico"""
        if not os.path.exists(self.debug_dir):
            os.makedirs(self.debug_dir, exist_ok=True)
            
        # Limitar el número de sesiones de debug antiguas (máximo 5)
        try:
            sessions = sorted([d for d in os.listdir(self.debug_dir) 
                             if os.path.isdir(os.path.join(self.debug_dir, d))])
            if len(sessions) > 5:
                for old_session in sessions[:-5]:
                    shutil.rmtree(os.path.join(self.debug_dir, old_session), ignore_errors=True)
        except Exception as e:
            log("DEBUG", "error", f"Error limpiando sesiones antiguas: {e}")

    def start_system_monitoring(self):
        """Inicia monitoreo periódico del sistema"""
        def monitor_loop():
            while True:
                try:
                    self.collect_system_info()
                    time.sleep(10)  # Recolectar información cada 10 segundos
                except Exception as e:
                    log("DEBUG", "error", f"Error en monitoreo del sistema: {e}")
                    time.sleep(30)  # Esperar más tiempo si hay error
                    
        # Iniciar en hilo separado
        monitoring_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitoring_thread.start()
        log("DEBUG", "info", "Monitoreo del sistema iniciado")

    def collect_system_info(self):
        """Recolecta información del sistema para diagnóstico"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Información de procesos
            with open(os.path.join(self.session_dir, f"ps_{timestamp}.txt"), 'w') as f:
                ps_output = subprocess.run(['ps', 'aux'], 
                                      stdout=subprocess.PIPE, 
                                      stderr=subprocess.PIPE,
                                      text=True).stdout
                f.write(ps_output)
            
            # Información de memoria
            with open(os.path.join(self.session_dir, f"memory_{timestamp}.txt"), 'w') as f:
                memory_output = subprocess.run(['free', '-m'], 
                                          stdout=subprocess.PIPE, 
                                          stderr=subprocess.PIPE,
                                          text=True).stdout
                f.write(memory_output)
            
            # Información de temperatura
            try:
                with open(os.path.join(self.session_dir, f"temp_{timestamp}.txt"), 'w') as f:
                    temp_output = subprocess.run(['vcgencmd', 'measure_temp'], 
                                            stdout=subprocess.PIPE, 
                                            stderr=subprocess.PIPE,
                                            text=True).stdout
                    f.write(temp_output)
            except:
                pass  # Ignorar si falla (por ejemplo, en entorno no-Raspberry)
            
            # Procesos MPV específicamente
            with open(os.path.join(self.session_dir, f"mpv_{timestamp}.txt"), 'w') as f:
                mpv_output = subprocess.run(['pgrep', '-a', 'mpv'], 
                                       stdout=subprocess.PIPE, 
                                       stderr=subprocess.PIPE,
                                       text=True).stdout
                f.write(f"MPV processes:\n{mpv_output}\n\n")
                
                # Si tenemos PID de MPV, obtener información detallada
                if mpv_output.strip():
                    for line in mpv_output.strip().split('\n'):
                        try:
                            pid = line.split()[0]
                            f.write(f"Detalles para PID {pid}:\n")
                            
                            # Estado del proceso
                            lsof_output = subprocess.run(['lsof', '-p', pid], 
                                                    stdout=subprocess.PIPE, 
                                                    stderr=subprocess.PIPE,
                                                    text=True).stdout
                            f.write(f"Open files:\n{lsof_output}\n\n")
                            
                        except Exception as e:
                            f.write(f"Error obteniendo detalles: {e}\n")
                
            # Si tenemos un proceso activo de player, registrar su tiempo de ejecución
            if hasattr(self, 'start_time') and self.player_process:
                runtime = time.time() - self.start_time
                with open(os.path.join(self.session_dir, f"runtime_{timestamp}.txt"), 'w') as f:
                    f.write(f"Tiempo de ejecución: {int(runtime)} segundos\n")
                    f.write(f"PID: {self.player_process.pid}\n")
                    f.write(f"Estado: {'Ejecutando' if self.player_process.poll() is None else f'Terminado ({self.player_process.poll()})'}\n")
                    
        except Exception as e:
            log("DEBUG", "error", f"Error recolectando información: {e}")

    def _kill_existing_players(self):
        """Mata cualquier proceso de reproducción existente"""
        try:
            subprocess.run(['pkill', '-9', 'vlc'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            subprocess.run(['pkill', '-9', 'cvlc'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            subprocess.run(['pkill', '-9', 'mpv'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
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
        
        # Capturar información de diagnóstico antes de detener
        if hasattr(self, 'start_time') and self.player_process:
            runtime = time.time() - self.start_time
            log("DEBUG", "info", f"Deteniendo reproductor después de {int(runtime)} segundos")
            
            # Intentar capturar detalles adicionales si está cerca del tiempo de congelación
            if 100 <= runtime <= 140:
                log("DEBUG", "warning", f"Deteniendo cerca del tiempo de congelación ({int(runtime)}s)")
                self.collect_system_info()  # Recolectar información extra
        
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
        
        # Recolectar información de diagnóstico antes del reinicio
        self.collect_system_info()
        
        # Detener el reproductor actual
        self.stop_player()
        
        # Pequeña pausa para que los procesos terminen por completo
        time.sleep(2)
        
        # Iniciar el reproductor de nuevo
        self.stream_video()

    def start_via_shell_script(self, srt_url):
        """Inicia el reproductor a través de un script shell independiente"""
        log("SHELL", "info", f"Iniciando VLC a través de shell con URL: {srt_url}")
        
        try:
            # Crear un script shell temporal con opciones de debug
            fd, script_path = tempfile.mkstemp(suffix='.sh')
            self.script_path = script_path
            log_file = os.path.join(self.session_dir, f"vlc_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
            
            with os.fdopen(fd, 'w') as f:
                f.write('#!/bin/bash\n\n')
                f.write('# Script generado automáticamente para VLC con diagnóstico\n')
                f.write(f'# Fecha: {time.strftime("%Y-%m-%d %H:%M:%S")}\n\n')
                
                # Comando para usar cvlc (VLC sin interfaz gráfica)
                f.write(f'cvlc "{srt_url}" \\\n')
                f.write('  --fullscreen \\\n')
                f.write('  --aout=alsa \\\n')
                f.write('  --alsa-audio-device=default \\\n')
                f.write('  --gain=1.0 \\\n')
                f.write('  --no-video-title-show \\\n')
                f.write('  --no-qt-privacy-ask \\\n')
                f.write('  --no-keyboard-events \\\n')
                f.write('  --sout-mux-caching=1500 \\\n')
                f.write('  --no-osd \\\n')
                f.write('  --network-caching=1500 \\\n')
                f.write('  --avcodec-hw=any \\\n')
                f.write(f'  --logfile="{log_file}" \\\n')
                f.write('  --file-logging \\\n')
                f.write('  --verbose=3\n')
                
                # Añadir código para recolectar información post-ejecución
                f.write('\n# Información post-ejecución\n')
                f.write('RESULT=$?\n')
                f.write(f'echo "VLC terminó con código: $RESULT" >> "{log_file}"\n')
                f.write(f'dmesg | tail -50 >> "{log_file}"\n')  # Últimas entradas del kernel
                
                # Eliminar el script después de ejecutarse
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
                
                # Iniciar VLC mediante script shell independiente
                log("PRUEBA", "info", "Iniciando VLC mediante script shell independiente")
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
                        # Recolectar información sobre la finalización
                        self.collect_system_info()
                    
                    self.stream_video()
                    start_iteration += 1
                else:
                    # Verificar cuánto tiempo lleva ejecutándose
                    runtime = time.time() - self.start_time
                    if int(runtime) % 30 == 0:  # Registrar cada 30 segundos
                        log("PRUEBA", "info", f"Proceso lleva {int(runtime)} segundos ejecutándose")
                        
                        # Verificar si VLC sigue ejecutándose
                        vlc_check = subprocess.run(
                            "pgrep vlc", 
                            shell=True, 
                            stdout=subprocess.PIPE, 
                            stderr=subprocess.PIPE
                        )
                        
                        if vlc_check.returncode != 0:
                            log("PRUEBA", "warning", "No se encontró proceso VLC a pesar de que el script sigue ejecutándose")
                            # Forzar reinicio
                            self.stop_player()
                            self.stream_video()
                
                # Dormir para no consumir CPU
                time.sleep(1)
                
            except Exception as e:
                log("SISTEMA", "error", f"Error en bucle principal: {e}")
                self._kill_existing_players()
                time.sleep(5)

    # Método requerido por main.py
    def stop_ffmpeg(self):
        """Método para compatibilidad con main.py"""
        self.stop_player() 