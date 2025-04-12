#!/bin/bash

# Verificar si se ejecuta como root
if [ "$EUID" -ne 0 ]; then 
    echo "Por favor, ejecuta el script como root (usando sudo)"
    exit 1
fi

echo "🚀 Iniciando configuración del sistema..."

# Detener el servicio si existe
if systemctl is-active --quiet srt-player; then
    echo "🛑 Deteniendo servicio existente..."
    systemctl stop srt-player
fi

# Instalar dependencias del sistema
echo "📦 Instalando dependencias del sistema..."
apt-get update
apt-get install -y \
    ffmpeg \
    python3-requests \
    python3-pip \
    python3-full \
    python3-opencv \
    python3-numpy

# Verificar instalación
echo "✅ Verificando instalación de Python y módulos..."
python3 -c "import requests; import cv2; import numpy; print('Módulos instalados correctamente')"

# 1. Servicio del player
echo "🔧 Configurando servicio del player..."
cat > /etc/systemd/system/srt-player.service << EOF
[Unit]
Description=SRT Player Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/srtRaspberryPlayer
Environment=PYTHONPATH=/root/srtRaspberryPlayer/src
ExecStart=/usr/bin/python3 -u src/main.py
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

# 7. Mostrar estado
echo "📊 Estado del servicio:"
systemctl status srt-player

# Configurar audio HDMI
echo "🔊 Configurando audio HDMI..."
apt-get install -y alsa-utils

# Configurar ALSA
echo "🔊 Configurando ALSA..."
cat > /etc/asound.conf << EOF
pcm.!default {
    type hw
    card 0
    device 1
}

ctl.!default {
    type hw
    card 0
}
EOF

# Habilitar módulos de sonido y cargarlos
echo "🔊 Habilitando módulos de sonido..."
modprobe snd-bcm2835
amixer cset numid=3 2  # 2 = HDMI, 1 = Analógico, 0 = Auto

# Verificar configuración de audio en config.txt
echo "🔊 Verificando configuración de audio..."
if ! grep -q "dtparam=audio=on" /boot/config.txt; then
    echo "dtparam=audio=on" >> /boot/config.txt
fi

# Añadir soporte gráfico y audio
if ! grep -q "vc4-kms-v3d" /boot/config.txt; then
    echo "dtoverlay=vc4-kms-v3d" >> /boot/config.txt
fi

# Configurar audio por defecto
echo "🔊 Configurando audio por defecto..."
cat > /etc/modprobe.d/alsa-base.conf << EOF
options snd-bcm2835 index=0
EOF

echo "✨ Instalación completada!"
echo "Para ver los logs en tiempo real: journalctl -u srt-player -f"