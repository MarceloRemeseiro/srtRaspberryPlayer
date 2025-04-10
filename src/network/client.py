import subprocess
import requests
import time
import socket
import os
from config.settings import PROXY_URL, DEVICE_ID, PROXY_CHECK_INTERVAL

# Variables globales
current_server_url = None
current_srt_url = None
last_proxy_check = 0

def get_local_ip():
    """Obtiene la IP local de una manera compatible con Raspberry Pi"""
    try:
        # Método principal para Raspberry Pi
        result = subprocess.check_output("hostname -I", shell=True).decode().strip()
        if result:
            return result.split()[0]
    except Exception as e:
        print(f"Error obteniendo IP local con hostname: {e}")
        try:
            # Método alternativo con socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception as e2:
            print(f"Error obteniendo IP local con socket: {e2}")
        
    # Si todo falla, devolver localhost
    return "127.0.0.1"

def get_public_ip():
    try:
        response = requests.get('https://api.ipify.org?format=json', timeout=5)
        return response.json()['ip']
    except Exception as e:
        print(f'Error obteniendo IP pública: {e}')
        return "0.0.0.0"

def should_check_proxy():
    """Determina si es hora de consultar el servidor proxy nuevamente"""
    global last_proxy_check
    current_time = time.time()
    
    # Primera vez o ha pasado suficiente tiempo
    if last_proxy_check == 0 or (current_time - last_proxy_check) > PROXY_CHECK_INTERVAL:
        last_proxy_check = current_time
        return True
    return False

def register_with_proxy():
    """Registra el dispositivo con el servidor proxy"""
    try:
        local_ip = get_local_ip()
        public_ip = get_public_ip()
        
        # Formato que espera el servidor según el endpoint
        data = {
            'id': DEVICE_ID,  # El servidor espera 'id' o 'mac'
            'ipPublica': public_ip  # El servidor espera 'ipPublica' o 'ip'
        }
        
        # Endpoint para registro en el proxy
        register_url = f'{PROXY_URL}/api/devices/register'
        print(f'\n[PROXY] Registrando dispositivo en: {register_url}')
        print(f'[PROXY] Datos: {data}')
        
        response = requests.post(register_url, json=data, timeout=5)
        response.raise_for_status()
        result = response.json()
        
        print(f'[PROXY] ✓ Dispositivo registrado en proxy. Resultado: {result.get("mensaje", "Sin mensaje")}')
        print(f'[PROXY] ✓ Estado del dispositivo: {result.get("status", "desconocido")}')
        
        # Si el dispositivo ya está asignado, obtenemos la URL de streaming
        if result.get("streamingUrl"):
            global current_srt_url
            current_srt_url = result.get("streamingUrl")
            print(f'[PROXY] ✓ URL SRT recibida directamente: {current_srt_url}')
        
        return True
    except Exception as e:
        print(f'[PROXY] ✗ Error registrando en proxy: {e}')
        return False

def get_server_url(force_check=False):
    """Obtiene la URL del servidor desde el proxy"""
    global current_server_url, last_proxy_check
    
    # Si tenemos una URL y no necesitamos refrescarla, la devolvemos
    if current_server_url and not force_check and not should_check_proxy():
        return current_server_url
    
    try:
        local_ip = get_local_ip()
        public_ip = get_public_ip()
        
        data = {
            'device_id': DEVICE_ID,
            'public_ip': public_ip,
            'local_ip': local_ip
        }
        
        proxy_url = f'{PROXY_URL}/api/server-config'
        print(f'\n[PROXY] Consultando servidor en: {proxy_url}')
        print(f'[PROXY] Datos: {data}')
        
        response = requests.post(proxy_url, json=data, timeout=5)
        response.raise_for_status()
        config_data = response.json()
        
        # Obtener SERVER_URL del proxy
        server_url = config_data.get('server_url')
        if server_url:
            print(f'[PROXY] ✓ Servidor asignado: {server_url}')
            # Actualizar la URL global si cambió
            if current_server_url != server_url:
                print(f'[PROXY] ⚡ Cambio de servidor detectado: {server_url}')
            current_server_url = server_url
            return server_url
        
        print('[PROXY] ✗ No se recibió URL de servidor válida')
        return None
            
    except Exception as e:
        print(f'[PROXY] ✗ Error consultando al proxy: {e}')
        # Si hay un error pero tenemos una URL anterior, la seguimos usando
        if current_server_url:
            print(f'[PROXY] ℹ Usando servidor anterior: {current_server_url}')
            return current_server_url
        return None

def register_device(status='ONLINE'):
    """Registra el dispositivo en el servidor central"""
    global current_srt_url
    
    # Si no tenemos servidor asignado, intentamos registrarnos en el proxy
    if not current_server_url:
        register_with_proxy()
        # Intentamos obtener la URL del servidor después del registro
        server_url = get_server_url(force_check=True)
    else:
        server_url = current_server_url
    
    # Si aún no tenemos URL de servidor, no podemos registrarnos
    if not server_url:
        print("[REGISTRO] ✗ No se pudo obtener URL del servidor, no se registrará el dispositivo")
        return None
    
    try:
        local_ip = get_local_ip()
        public_ip = get_public_ip()
        
        # Formato que espera el servidor
        data = {
            'id': DEVICE_ID,
            'ipPublica': public_ip,
            'status': status
        }
        
        register_url = f'{server_url}/api/devices/register'
        print(f'[REGISTRO] Registrando estado en: {register_url}')
        print(f'[REGISTRO] Datos: {data}')
        
        response = requests.post(register_url, json=data)
        response.raise_for_status()
        result = response.json()
        
        print(f'[REGISTRO] ✓ Dispositivo {DEVICE_ID} actualizado: {result.get("mensaje", "Sin mensaje")}')
        print(f'[REGISTRO] ✓ Estado: {result.get("status", "desconocido")}')
        
        # Si la respuesta incluye directamente la URL de streaming, la usamos
        if result.get("streamingUrl"):
            current_srt_url = result.get("streamingUrl")
            print(f'[REGISTRO] ✓ URL SRT recibida directamente: {current_srt_url}')
            
        return result
            
    except Exception as e:
        print(f'[REGISTRO] ✗ Error registrando dispositivo: {e}')
        return None

def get_srt_url():
    """Obtiene la URL SRT del servidor central"""
    global current_srt_url
    
    # Primero comprobamos si debemos refrescar la conexión con el proxy
    if should_check_proxy():
        # Registramos el dispositivo y verificamos si obtenemos la URL directamente
        result = register_device()
        if result and result.get("streamingUrl"):
            current_srt_url = result.get("streamingUrl")
            return current_srt_url
    
    # Si ya tenemos una URL SRT, la devolvemos
    if current_srt_url:
        return current_srt_url
    
    # Si no tenemos servidor asignado, no podemos obtener el SRT
    if not current_server_url:
        print("[CONFIG] ✗ No se pudo obtener URL del servidor, no se consultará el SRT")
        return None
    
    try:
        # Consultamos el endpoint de configuración
        config_url = f'{current_server_url}/api/devices/{DEVICE_ID}/config'
        print(f'\n[CONFIG] Consultando configuración en: {config_url}')
        
        response = requests.get(config_url)
        response.raise_for_status()
        data = response.json()
        
        srt_url = data.get('srt_url')
        if srt_url:
            print(f'[CONFIG] ✓ URL SRT recibida: {srt_url}')
            current_srt_url = srt_url
            return srt_url
        
        print('[CONFIG] ✗ No hay SRT configurado')
        return None
            
    except Exception as e:
        print(f'[CONFIG] ✗ Error obteniendo configuración: {e}')
        # Si hay un error pero tenemos una URL anterior, la seguimos usando
        if current_srt_url:
            print(f'[CONFIG] ℹ Usando URL SRT anterior: {current_srt_url}')
            return current_srt_url
        return None 