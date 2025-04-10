import os
from pathlib import Path
import subprocess
import uuid

# Rutas base
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ASSETS_DIR = BASE_DIR / 'assets'

# Archivo para almacenar el ID persistente
DEVICE_ID_FILE = BASE_DIR / 'device_id.txt'

def get_device_id():
    try:
        # Si ya tenemos un ID almacenado, usarlo
        if os.path.exists(DEVICE_ID_FILE):
            with open(DEVICE_ID_FILE, 'r') as f:
                device_id = f.read().strip()
                if device_id:
                    return device_id

        # Obtener el número de serie de la Raspberry Pi
        cmd = "cat /proc/cpuinfo | grep Serial | cut -d ' ' -f 2"
        serial = subprocess.check_output(cmd, shell=True).decode().strip()
        if serial:
            # Toma los últimos 6 caracteres del serial
            device_id = f'PLAYER_{serial[-6:].upper()}'
        else:
            # Si no podemos obtener el serial, usar un ID único
            device_id = f'PLAYER_{uuid.uuid4().hex[:6].upper()}'
            
        # Guardar el ID para uso futuro
        with open(DEVICE_ID_FILE, 'w') as f:
            f.write(device_id)
            
        return device_id
    except Exception as e:
        print(f"Error al obtener serial: {e}")
        # Si falla, usa un valor por defecto
        return 'PLAYER_000000'

DEVICE_ID = get_device_id()
print(f"Iniciando con DEVICE_ID: {DEVICE_ID}")

# URL del servidor proxy local - AJUSTA ESTO A LA IP DE TU SERVIDOR
# Para desarrollo local (pruebas):
# PROXY_URL = 'http://localhost:3000'
# Para producción (reemplaza con la IP o dominio de tu servidor):
PROXY_URL = 'http://192.168.1.51:3000'

# Intervalos de consulta (en segundos)
PROXY_CHECK_INTERVAL = 60   # Consultar servidor proxy cada 60 segundos
CONFIG_CHECK_INTERVAL = 5   # Consultar configuración SRT cada 5 segundos

# El SERVER_URL se establecerá dinámicamente
SERVER_URL = None

CONFIG_CHECK_INTERVAL = 5   # Segundos entre consultas al servidor 