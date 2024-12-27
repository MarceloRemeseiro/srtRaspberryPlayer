#!/bin/bash

# Obtener la versión del tag más reciente y aumentarla
VERSION=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0")
NEXT_VERSION=$(echo $VERSION | awk -F. -v OFS=. '{$NF += 1;print}')

echo "🚀 Building version: $NEXT_VERSION"

# Construir la imagen con latest y version tag
docker build -t ghcr.io/marceloremeseiro/srtraspberryplayercontainer:latest \
             -t ghcr.io/marceloremeseiro/srtraspberryplayercontainer:$NEXT_VERSION .

if [ $? -eq 0 ]; then
    echo "✅ Build completado. Iniciando push..."
    
    # Push de ambas tags
    docker push ghcr.io/marceloremeseiro/srtraspberryplayercontainer:latest
    docker push ghcr.io/marceloremeseiro/srtraspberryplayercontainer:$NEXT_VERSION
    
    # Crear y pushear el tag de git
    git tag $NEXT_VERSION
    git push origin $NEXT_VERSION
    
    echo "✨ Todo completado!"
else
    echo "❌ Error en el build"
    exit 1
fi 