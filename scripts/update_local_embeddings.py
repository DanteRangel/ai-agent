#!/usr/bin/env python3

import os
import sys
from pathlib import Path

# Add app directory to Python path
app_dir = str(Path(__file__).parent.parent)
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

from datetime import datetime, timedelta
import boto3
from openai import OpenAI

from app.functions.update_embeddings.handler import _process_batch
from app.core.services.car_recommender import CarRecommender

def verify_local_dynamodb():
    """Verifica que DynamoDB local esté corriendo y accesible."""
    try:
        # Intentar conectar a DynamoDB local
        local_dynamodb = boto3.resource(
            'dynamodb',
            endpoint_url='http://localhost:8000',
            region_name='us-east-1',
            aws_access_key_id='dummy',
            aws_secret_access_key='dummy'
        )
        # Intentar listar tablas para verificar conexión
        local_dynamodb.meta.client.list_tables()
        return local_dynamodb
    except Exception as e:
        print("[ERROR] No se pudo conectar a DynamoDB local")
        print(f"[ERROR] Asegúrate que DynamoDB local esté corriendo en http://localhost:8000")
        print(f"[ERROR] Detalles: {str(e)}")
        sys.exit(1)

def verify_local_tables(dynamodb):
    """Verifica que las tablas necesarias existan en DynamoDB local."""
    required_tables = [
        "kavak-ai-agent-catalog-dev",
        "kavak-ai-agent-embeddings-dev"
    ]
    
    existing_tables = dynamodb.meta.client.list_tables()['TableNames']
    missing_tables = [table for table in required_tables if table not in existing_tables]
    
    if missing_tables:
        print("[ERROR] Faltan las siguientes tablas en DynamoDB local:")
        for table in missing_tables:
            print(f"[ERROR] - {table}")
        print("\n[ERROR] Ejecuta primero el script create_local_tables.sh para crear las tablas")
        sys.exit(1)

# Verificar que estamos en entorno local
if os.environ.get('STAGE') and os.environ['STAGE'] != 'dev':
    print("[ERROR] Este script solo debe ejecutarse en entorno local (STAGE=dev)")
    print("[ERROR] Por seguridad, no se permite ejecutar en otros entornos")
    sys.exit(1)

# Forzar entorno local
os.environ["STAGE"] = "dev"
os.environ["CATALOG_TABLE"] = "kavak-ai-agent-catalog-dev"
os.environ["EMBEDDINGS_TABLE"] = "kavak-ai-agent-embeddings-dev"
os.environ["MODEL_NAME"] = "gpt-4-turbo-preview"

# Verificar DynamoDB local
print("🔍 Verificando conexión a DynamoDB local...")
dynamodb = verify_local_dynamodb()
print("✅ Conexión a DynamoDB local exitosa")

# Verificar tablas necesarias
print("\n🔍 Verificando tablas necesarias...")
verify_local_tables(dynamodb)
print("✅ Todas las tablas necesarias existen")

def get_existing_embeddings():
    """Obtiene los embeddings existentes de la tabla local."""
    try:
        embeddings_table = dynamodb.Table(os.environ["EMBEDDINGS_TABLE"])
        response = embeddings_table.scan()
        return {item["stockId"]: item for item in response.get("Items", [])}
    except Exception as e:
        print(f"[ERROR] Error obteniendo embeddings existentes: {str(e)}")
        return {}

def get_catalog_cars():
    """Obtiene los autos del catálogo local."""
    try:
        catalog_table = dynamodb.Table(os.environ["CATALOG_TABLE"])
        response = catalog_table.scan()
        return response.get("Items", [])
    except Exception as e:
        print(f"[ERROR] Error obteniendo catálogo: {str(e)}")
        return []

def main():
    """Ejecuta la actualización de embeddings en local."""
    if not os.environ.get("OPENAI_API_KEY"):
        print("[ERROR] La variable de entorno OPENAI_API_KEY no está configurada")
        print("Por favor, configura tu API key de OpenAI:")
        print("export OPENAI_API_KEY='tu-api-key'")
        sys.exit(1)

    print("\n🚀 Iniciando actualización de embeddings en entorno local...")
    
    # Inicializar servicios
    recommender = CarRecommender()
    recommender.dynamodb = dynamodb  # Usar DynamoDB local verificada
    recommender.catalog_db = dynamodb.Table(os.environ["CATALOG_TABLE"])
    recommender.embeddings_db = dynamodb.Table(os.environ["EMBEDDINGS_TABLE"])
    recommender.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    
    # Obtener datos
    print("\n📥 Obteniendo datos...")
    existing_embeddings = get_existing_embeddings()
    cars = get_catalog_cars()
    
    if not cars:
        print("[ERROR] No se encontraron autos en el catálogo local")
        sys.exit(1)
        
    print(f"✅ Se encontraron {len(cars)} autos en el catálogo")
    print(f"✅ Se encontraron {len(existing_embeddings)} embeddings existentes")
    
    # Configurar parámetros
    now = datetime.now()
    update_threshold = (now - timedelta(days=1)).isoformat()  # Actualizar si tiene más de 1 día
    
    # Procesar en lotes
    print("\n🔄 Procesando autos...")
    total_processed, total_updated, total_errors = _process_batch(
        recommender=recommender,
        cars=cars,
        existing_embeddings=existing_embeddings,
        update_threshold=update_threshold,
        now=now
    )
    
    # Mostrar resumen
    print("\n✨ Resumen final:")
    print(f"- Total procesados: {total_processed}")
    print(f"- Total actualizados: {total_updated}")
    print(f"- Total errores: {total_errors}")
    
    if total_errors > 0:
        print("\n⚠️  Se encontraron errores durante la actualización")
        sys.exit(1)
    else:
        print("\n✅ Actualización completada exitosamente")

if __name__ == '__main__':
    main() 