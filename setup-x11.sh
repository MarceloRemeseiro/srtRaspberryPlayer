#!/bin/bash

# Script para configurar entorno X11 para VLC en Raspberry Pi
echo "Configurando entorno X11 para VLC en Raspberry Pi..."

# Instalar X11 y componentes necesarios
echo "Instalando X11 y componentes necesarios..."
apt-get update
apt-get install -y xorg x11-xserver-utils

# Comprobar si lightdm está instalado, si no, instalarlo
if ! dpkg -l | grep -q lightdm; then
    echo "Instalando LightDM..."
    apt-get install -y lightdm
fi

# Configurar permisos para el usuario pi
echo "Configurando permisos para usuario pi..."
usermod -a -G video,tty pi
chmod 666 /dev/fb0 2>/dev/null || true
# Dar permisos a los dispositivos DRI si existen
if [ -d /dev/dri ]; then
    chmod 666 /dev/dri/* 2>/dev/null || true
fi

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

# Crear archivo Xsession para el usuario pi
echo "Creando archivo Xsession..."
cat > /home/pi/.xsession << EOF
#!/bin/sh
# Archivo Xsession para pi
xset s off
xset -dpms
xset s noblank
EOF
chmod +x /home/pi/.xsession
chown pi:pi /home/pi/.xsession

# Crear .Xauthority si no existe
touch /home/pi/.Xauthority
chown pi:pi /home/pi/.Xauthority

# Actualizar /boot/config.txt para configuración de pantalla
echo "Configurando pantalla en /boot/config.txt..."
if ! grep -q "^hdmi_force_hotplug=1" /boot/config.txt; then
    echo "hdmi_force_hotplug=1" >> /boot/config.txt
fi
if ! grep -q "^config_hdmi_boost=4" /boot/config.txt; then
    echo "config_hdmi_boost=4" >> /boot/config.txt
fi

# Iniciar X11 si no está corriendo
if ! pgrep Xorg > /dev/null; then
    echo "Iniciando servidor X11..."
    systemctl start lightdm
fi

# Reiniciar servicio srt-player-user
echo "Reiniciando servicio srt-player-user..."
systemctl restart srt-player-user

echo "Configuración completada."
echo "Para ver logs del servicio usa: sudo journalctl -u srt-player-user -f" 