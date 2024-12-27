import subprocess
import requests
from config.settings import SERVER_URL, DEVICE_ID

def get_public_ip():
    try:
        response = requests.get('https://api.ipify.org?format=json', timeout=5)
        return response.json()['ip']
    except Exception as e:
        print(f'Error obteniendo IP pública: {e}')
        return None

def register_device(status='ONLINE'):
    try:
        local_ip = subprocess.check_output(['hostname', '-I']).decode().split()[0].strip()
        public_ip = get_public_ip()
        
        data = {
            'device_id': DEVICE_ID,
            'local_ip': local_ip,
            'public_ip': public_ip,
            'status': status
        }
        
        register_url = f'{SERVER_URL}/api/devices'
        print(f'Registrando estado en: {register_url}')
        print(f'Datos: {data}')
        
        response = requests.post(register_url, json=data)
        response.raise_for_status()
        print(f'Dispositivo {DEVICE_ID} actualizado. Status: {status}')
            
    except Exception as e:
        print(f'Error registrando dispositivo: {e}')

def get_srt_url():
    try:
        config_url = f'{SERVER_URL}/api/devices/{DEVICE_ID}/config'
        print(f'\n[CONFIG] Consultando configuración en: {config_url}')
        
        response = requests.get(config_url)
        response.raise_for_status()
        data = response.json()
        
        srt_url = data.get('srt_url')
        if srt_url:
            print(f'[CONFIG] ✓ URL SRT recibida: {srt_url}')
            return srt_url
        
        print('[CONFIG] ✗ No hay SRT configurado')
        return None
            
    except Exception as e:
        print('[CONFIG] ✗ Error obteniendo configuración')
        return None 