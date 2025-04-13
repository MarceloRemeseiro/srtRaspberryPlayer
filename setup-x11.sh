#!/bin/bash

# Script para configurar entorno X11 para VLC en Raspberry Pi
echo "Configurando entorno X11 para VLC en Raspberry Pi..."

# Instalar X11 y componentes necesarios
echo "Instalando X11 y componentes necesarios..."
apt-get update
apt-get install -y xorg lightdm x11-xserver-utils

# Configurar permisos para el usuario pi
echo "Configurando permisos para usuario pi..."
usermod -a -G video,tty pi
chmod 666 /dev/fb0
chmod 666 /dev/dri/* 2>/dev/null || true

# Crear configuración de VLC para el usuario pi
echo "Creando configuración de VLC..."
mkdir -p /home/pi/.config/vlc
cat > /home/pi/.config/vlc/vlcrc << EOF
[qt]
qt-privacy-ask=0

[core]
video-title-show=0
quiet=1

[x11]
display=:0
EOF

# Asegurarse de que el usuario pi sea propietario de sus archivos
chown -R pi:pi /home/pi/.config

# Configurar arranque automático de X11
echo "Configurando arranque automático de X11..."
systemctl enable lightdm

# Crear .Xauthority si no existe
touch /home/pi/.Xauthority
chown pi:pi /home/pi/.Xauthority

# Iniciar X11 si no está corriendo (sin esperar)
if ! pgrep Xorg > /dev/null; then
    echo "Iniciando servidor X11..."
    systemctl start lightdm
fi

# Reiniciar servicio srt-player-user
echo "Reiniciando servicio srt-player-user..."
systemctl restart srt-player-user

echo "Configuración completada. Verifica que VLC se muestre en la pantalla HDMI." 