import subprocess
import requests
import time
import socket
import os
from datetime import datetime
from config.settings import PROXY_URL, DEVICE_ID, PROXY_CHECK_INTERVAL, IS_DEV

# Variables globales
current_server_url = None
current_srt_url = None
last_proxy_check = 0
device_status = 'OFFLINE'

def log(category, status, message):
    """Función para logs consistentes"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    status_symbol = "✓" if status == "success" else "✗" if status == "error" else "ℹ"
    print(f"[{timestamp}] [{category}] {status_symbol} {message}")

def get_local_ip():
    """Obtiene la IP local o devuelve un placeholder en desarrollo"""
    if IS_DEV:
        return "DEV_ENV"
    try:
        result = subprocess.check_output("hostname -I", shell=True).decode().strip()
        if result:
            return result.split()[0]
    except Exception as e:
        log("SISTEMA", "error", f"Error obteniendo IP local: {e}")
        return "UNKNOWN"

def get_public_ip():
    """Obtiene la IP pública o devuelve un placeholder en desarrollo"""
    if IS_DEV:
        return "DEV_ENV"
    try:
        response = requests.get('https://api.ipify.org?format=json', timeout=5)
        return response.json()['ip']
    except Exception as e:
        log("SISTEMA", "error", f"Error obteniendo IP pública: {e}")
        return "UNKNOWN"

def get_server_url(force_check=False):
    """Obtiene la URL del servidor desde el proxy"""
    global current_server_url, last_proxy_check
    
    if current_server_url and not force_check and not should_check_proxy():
        return current_server_url
    
    try:
        data = {
            'mac': DEVICE_ID,
            'ip': get_public_ip()
        }
        
        proxy_url = f'{PROXY_URL}/api/server-config'
        log("SERVIDOR", "info", f"Consultando servidor en: {proxy_url}")
        
        response = requests.post(proxy_url, json=data, timeout=5)
        response.raise_for_status()
        config_data = response.json()
        
        # Obtener la URL de streaming del proxy
        if config_data.get('streamingUrl'):
            server_url = config_data.get('streamingUrl')
            if current_server_url != server_url:
                log("SERVIDOR", "success", f"Nuevo servidor asignado: {server_url}")
            current_server_url = server_url
            return server_url
        
        log("SERVIDOR", "info", "Sin servidor asignado")
        return None
            
    except Exception as e:
        log("SERVIDOR", "error", f"Error consultando servidor: {e}")
        if current_server_url:
            log("SERVIDOR", "info", f"Usando servidor anterior: {current_server_url}")
            return current_server_url
        return None

def register_with_proxy():
    """Registra el dispositivo con el servidor proxy"""
    global current_server_url
    try:
        data = {
            'mac': DEVICE_ID,
            'ip': get_public_ip()
        }
        
        register_url = f'{PROXY_URL}/api/devices/register'
        log("PROXY", "info", f"Registrando en proxy: {register_url}")
        
        response = requests.post(register_url, json=data, timeout=5)
        response.raise_for_status()
        result = response.json()
        
        log("PROXY", "info", f"Respuesta del proxy: {result}")
        
        # Si el dispositivo está asignado, actualizar la URL del servidor
        if result.get('status') == 'assigned' and result.get('streamingUrl'):
            # La URL base será algo como http://192.168.1.51:3001
            current_server_url = result.get('streamingUrl')
            log("PROXY", "success", f"URL streaming recibida: {current_server_url}")
            
        if result.get('status'):
            log("PROXY", "info", f"Estado del dispositivo: {result.get('status')}")
            
        return True
    except Exception as e:
        log("PROXY", "error", f"Error en registro: {e}")
        return False

def register_with_streaming_server(server_url):
    """Registra el dispositivo con el servidor de streaming y actualiza su estado"""
    global current_srt_url, device_status
    
    try:
        if not server_url.endswith('/'):
            server_url += '/'
            
        register_url = f'{server_url}api/devices'
        log("STREAMING", "info", f"Actualizando estado en: {register_url}")
        
        data = {
            'dispositivoId': DEVICE_ID,
            'nombre': f'Raspberry {DEVICE_ID}',
            'inputSrt': 'pending',
            'ipPublica': '0.0.0.0'  # Valor por defecto temporal
        }
        
        response = requests.post(register_url, json=data, timeout=5)
        
        if response.status_code not in [200, 409]:
            log("STREAMING", "error", f"Error {response.status_code}: {response.text}")
            device_status = 'OFFLINE'
            return False
            
        result = response.json()
        log("STREAMING", "info", f"Respuesta del servidor: {result}")
        
        if result.get('success'):
            device_status = result.get('status', 'ONLINE')
            
            # Actualizar URL SRT si está disponible
            if result.get('streamingUrl'):
                current_srt_url = result.get('streamingUrl')
                log("STREAMING", "success", f"URL SRT asignada: {current_srt_url}")
                device_status = 'ACTIVE'
            
            log("STREAMING", "success", f"Estado: {device_status}")
            return True
            
        else:
            device_status = 'OFFLINE'
            current_srt_url = None
            log("STREAMING", "error", f"Error: {result.get('error', 'Sin mensaje')}")
            return False
        
    except Exception as e:
        log("STREAMING", "error", f"Error en registro: {e}")
        device_status = 'OFFLINE'
        current_srt_url = None
        return False

def register_device(status='ONLINE'):
    """Registra el dispositivo en el servidor de streaming"""
    global current_server_url, device_status
    
    # Intentar registro en proxy primero
    log("REGISTRO", "info", "Intentando registro en proxy...")
    
    try:
        data = {
            'id': DEVICE_ID,
            'ipPublica': '0.0.0.0'  # Valor por defecto temporal
        }
        
        response = requests.post(
            f"{PROXY_URL}/api/devices/register",
            json=data,
            timeout=5
        )
        
        if response.status_code != 200:
            log("PROXY", "error", f"Error {response.status_code}: {response.text}")
            device_status = 'OFFLINE'
            current_server_url = None
            return False
            
        result = response.json()
        log("PROXY", "info", f"Respuesta del proxy: {result}")
        
        # Actualizar estado según el proxy
        device_status = result.get('status', 'unassigned')
        
        # Solo si está asignado continuamos
        if device_status == 'assigned':
            current_server_url = result.get('streamingUrl')
            if current_server_url:
                log("PROXY", "success", f"URL streaming recibida: {current_server_url}")
                # Solo ahora intentamos registro con streaming
                return register_with_streaming_server(current_server_url)
        else:
            log("PROXY", "info", "Dispositivo no asignado, esperando asignación")
            current_server_url = None
            return False
            
    except Exception as e:
        log("PROXY", "error", f"Error en registro: {e}")
        device_status = 'OFFLINE'
        current_server_url = None
        return False

def get_srt_url():
    """Función principal para obtener la URL SRT"""
    global current_srt_url, device_status
    
    # Actualizamos estado si es necesario
    if should_check_proxy():
        register_device()
    
    # Verificamos si tenemos URL y estado válido
    if current_srt_url and device_status in ['ACTIVE', 'assigned']:
        return current_srt_url
    
    log("SRT", "info", f"No hay URL SRT disponible - Estado: {device_status}")
    return None

def should_check_proxy():
    """Determina si es hora de actualizar el estado"""
    global last_proxy_check
    current_time = time.time()
    
    # Actualizamos el estado cada minuto
    if last_proxy_check == 0 or (current_time - last_proxy_check) > 60:
        last_proxy_check = current_time
        return True
    return False

# Asegurarnos de exportar todas las funciones necesarias
__all__ = [
    'register_device',
    'register_with_proxy',
    'get_server_url',
    'get_srt_url',
    'log'
] 