#!/usr/bin/env python3
import os
import subprocess
import sys

def install_requirements(layer_path):
    requirements_file = os.path.join(layer_path, 'requirements.txt')
    python_path = os.path.join(layer_path, 'python')
    
    # Crear directorio python si no existe
    os.makedirs(python_path, exist_ok=True)
    
    # Usar Python 3.9 para instalar las dependencias
    python_cmd = 'python3.9'
    try:
        subprocess.run([python_cmd, '--version'], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"Error: {python_cmd} no está instalado. Por favor instala Python 3.9")
        sys.exit(1)
    
    # Instalar requirements en el directorio python
    subprocess.run([
        python_cmd,
        '-m', 
        'pip', 
        'install', 
        '--upgrade',
        'pip',
        'setuptools',
        'wheel'
    ], check=True)
    
    subprocess.run([
        python_cmd,
        '-m', 
        'pip', 
        'install', 
        '-r', requirements_file,
        '-t', python_path
    ], check=True)
    
    print(f"Dependencias instaladas en {layer_path}")

def main():
    # Instalar dependencias para cada layer
    layers = ['base', 'heavy']
    for layer in layers:
        layer_path = os.path.join('layers', layer)
        install_requirements(layer_path)

if __name__ == '__main__':
    main() 