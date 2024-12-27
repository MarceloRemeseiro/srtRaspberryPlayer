# Usar una imagen base de Python
FROM python:3.9-slim

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Crear directorios
WORKDIR /opt/srt-player-python

# Copiar archivos del proyecto
COPY . .

# Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# Crear script de entrada
RUN echo '#!/bin/sh' > /entrypoint.sh && \
    echo '[ -f /sys/class/graphics/fbcon/cursor_blink ] && echo 0 > /sys/class/graphics/fbcon/cursor_blink' >> /entrypoint.sh && \
    echo 'export DEVICE_ID="PLAYER_$(python -c "import random; print(f\"{random.randint(1,999):03d}\")")"' >> /entrypoint.sh && \
    echo 'echo "Starting with DEVICE_ID: $DEVICE_ID"' >> /entrypoint.sh && \
    echo 'python src/main.py' >> /entrypoint.sh && \
    chmod +x /entrypoint.sh

# Comando de inicio
ENTRYPOINT ["/entrypoint.sh"] 