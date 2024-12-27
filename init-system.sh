#!/bin/bash

# Verificar si se ejecuta como root
if [ "$EUID" -ne 0 ]; then 
    echo "Por favor, ejecuta el script como root (usando sudo)"
    exit 1
fi

echo "🚀 Iniciando configuración del sistema..."

# Instalar solo ffmpeg si no está instalado
if ! command -v ffmpeg &> /dev/null; then
    echo "📦 Instalando ffmpeg..."
    apt-get update
    apt-get install -y ffmpeg
fi

# Verificar versión de Python
PYTHON_VERSION=$(python3 --version)
echo "ℹ️ Usando $PYTHON_VERSION"

# Instalar requisitos de Python
echo "📦 Instalando dependencias de Python..."
python3 -m pip install -r requirements.txt

# 1. Servicio del player
echo "🔧 Configurando servicio del player..."
cat > /etc/systemd/system/srt-player.service << EOF
[Unit]
Description=SRT Player Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$(pwd)
Environment=PYTHONPATH=$(pwd)
ExecStart=/usr/bin/python3 src/main.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# 2. Servicio para deshabilitar cursor
echo "🖥️ Configurando servicio del cursor..."
cat > /etc/systemd/system/disable-cursor.service << EOF
[Unit]
Description=Disable cursor on framebuffer
After=getty.target

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'echo 0 > /sys/class/graphics/fbcon/cursor_blink'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

# 3. Configurar cmdline.txt si no está ya configurado
echo "⚙️ Configurando cmdline.txt..."
if ! grep -q "vt.global_cursor_default=0" /boot/cmdline.txt; then
    sed -i 's/$/ vt.global_cursor_default=0 logo.nologo consoleblank=0/' /boot/cmdline.txt
fi

# 4. Recargar systemd
echo "🔄 Recargando systemd..."
systemctl daemon-reload

# 5. Habilitar servicios
echo "✅ Habilitando servicios..."
systemctl enable srt-player
systemctl enable disable-cursor

# 6. Iniciar servicios
echo "▶️ Iniciando servicios..."
systemctl start disable-cursor
systemctl start srt-player

echo "✨ Instalación completada!"
echo "Para ver el estado del servicio: systemctl status srt-player"
echo "Para ver los logs: journalctl -u srt-player -f"