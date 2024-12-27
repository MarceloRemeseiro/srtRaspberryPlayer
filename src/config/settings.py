import os
from pathlib import Path
import subprocess

# Rutas base
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ASSETS_DIR = BASE_DIR / 'assets'

# Configuración
def get_device_id():
    try:
        # Obtener el número de serie de la Raspberry Pi
        cmd = "cat /proc/cpuinfo | grep Serial | cut -d ' ' -f 2"
        serial = subprocess.check_output(cmd, shell=True).decode().strip()
        if serial:
            # Toma los últimos 6 caracteres del serial
            return f'PLAYER_{serial[-6:].upper()}'
    except Exception as e:
        print(f"Error al obtener serial: {e}")
        # Si falla, usa un valor por defecto
        return 'PLAYER_000000'

DEVICE_ID = get_device_id()
print(f"Iniciando con DEVICE_ID: {DEVICE_ID}")
SERVER_URL = 'https://central.streamingpro.es'
CONFIG_CHECK_INTERVAL = 5   # Segundos entre consultas al servidor 