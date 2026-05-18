#!/bin/bash
# Casa Monarca - Setup Inicial
# Script para inicializar el proyecto (macOS/Linux)

set -e

echo "=== Casa Monarca - Setup Inicial ==="
echo ""

# 1. Crear entorno virtual
if [ ! -d ".venv" ]; then
    echo "▶️  Creando entorno virtual..."
    python3 -m venv .venv
    echo "✅ Entorno virtual creado"
else
    echo "✓ Entorno virtual ya existe"
fi

# 2. Activar entorno virtual
echo "▶️  Activando entorno virtual..."
source .venv/bin/activate

# 3. Actualizar pip
echo "▶️  Actualizando pip, setuptools y wheel..."
pip install --upgrade pip setuptools wheel > /dev/null 2>&1
echo "✅ pip actualizado"

# 4. Instalar dependencias
echo "▶️  Instalando dependencias desde requirements.txt..."
pip install -r requirements.txt
echo "✅ Dependencias instaladas"

# 5. Crear .env si no existe
if [ ! -f ".env" ]; then
    echo "▶️  Creando .env desde .env.example..."
    cp .env.example .env
    echo "⚠️  Edita .env con tus valores antes de ejecutar la aplicación"
else
    echo "✓ .env ya existe"
fi

# 6. Generar clave de cifrado si no existe
if [ ! -f "key.key" ]; then
    echo "▶️  Generando clave de cifrado..."
    python generate_key.py
    echo "✅ Clave de cifrado generada"
else
    echo "✓ key.key ya existe"
fi

# 7. Crear estructura de carpetas
echo "▶️  Creando estructura de carpetas..."
mkdir -p certs backups logs
echo "✅ Carpetas creadas: certs/, backups/, logs/"

# 8. Información final
echo ""
echo "=========================================="
echo "✅ Setup completado exitosamente"
echo "=========================================="
echo ""
echo "Próximos pasos:"
echo "  1. Edita .env con tus valores:"
echo "     nano .env"
echo ""
echo "  2. Activa el entorno virtual:"
echo "     source .venv/bin/activate"
echo ""
echo "  3. Ejecuta la aplicación:"
echo "     python app.py"
echo ""
echo "Notas:"
echo "  - La base de datos se inicializa automáticamente al ejecutar app.py"
echo "  - Asegúrate de tener Python 3.10+ instalado"
echo "  - Para más información, consulta README.md"
echo ""
