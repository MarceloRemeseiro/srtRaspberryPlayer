import requests
import time
import uuid
import socket

# Configuración de prueba
PROXY_URL = "http://localhost:3000"  # URL de tu servidor local
DEVICE_ID = f"PLAYER_TEST{uuid.uuid4().hex[:6].upper()}"  # ID de prueba

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"

def get_public_ip():
    try:
        response = requests.get('https://api.ipify.org?format=json', timeout=5)
        return response.json()['ip']
    except Exception as e:
        print(f'Error obteniendo IP pública: {e}')
        return "0.0.0.0"

def test_server_config():
    """Prueba el endpoint server-config"""
    print("\n1. Probando /api/server-config...")
    
    local_ip = get_local_ip()
    public_ip = get_public_ip()
    
    data = {
        'device_id': DEVICE_ID,
        'public_ip': public_ip,
        'local_ip': local_ip
    }
    
    try:
        response = requests.post(f"{PROXY_URL}/api/server-config", json=data, timeout=5)
        response.raise_for_status()
        result = response.json()
        
        print(f"✅ Éxito: Recibida URL del servidor: {result.get('server_url')}")
        return result.get('server_url')
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def test_register_device(server_url):
    """Prueba el endpoint para registrar el dispositivo"""
    print("\n2. Probando registro de dispositivo...")
    
    if not server_url:
        print("❌ No se puede continuar sin URL del servidor")
        return False
    
    local_ip = get_local_ip()
    public_ip = get_public_ip()
    
    data = {
        'device_id': DEVICE_ID,
        'public_ip': public_ip,
        'local_ip': local_ip,
        'status': 'TESTING'
    }
    
    try:
        register_url = f"{server_url}/api/devices/register"
        print(f"Enviando datos a: {register_url}")
        response = requests.post(register_url, json=data, timeout=5)
        response.raise_for_status()
        result = response.json()
        
        print(f"✅ Éxito: Dispositivo {DEVICE_ID} registrado")
        print(f"   Estado: {result.get('status')}")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_get_config(server_url):
    """Prueba el endpoint para obtener la configuración SRT"""
    print("\n3. Probando obtención de configuración SRT...")
    
    if not server_url:
        print("❌ No se puede continuar sin URL del servidor")
        return
    
    try:
        config_url = f"{server_url}/api/devices/{DEVICE_ID}/config"
        print(f"Consultando configuración en: {config_url}")
        response = requests.get(config_url, timeout=5)
        
        if response.status_code == 200:
            result = response.json()
            srt_url = result.get('srt_url')
            print(f"✅ Éxito: URL SRT recibida: {srt_url}")
        else:
            print(f"ℹ️ Aviso: Estado {response.status_code} - {response.text}")
            print("   Esto es normal si el dispositivo no está asignado a un usuario todavía")
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    print(f"🧪 Iniciando pruebas con ID de dispositivo: {DEVICE_ID}")
    
    # Prueba 1: Obtener URL del servidor
    server_url = test_server_config()
    
    # Prueba 2: Registrar dispositivo
    if server_url:
        registered = test_register_device(server_url)
        
        # Prueba 3: Obtener configuración SRT
        if registered:
            test_get_config(server_url)
    
    print("\n🏁 Pruebas completadas")
    print(f"   ID del dispositivo usado: {DEVICE_ID}")
    print("   Revisa el panel de administración para ver el dispositivo registrado")

if __name__ == "__main__":
    main() 