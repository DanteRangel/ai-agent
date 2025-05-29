import os
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any
from core.services.car_recommender import CarRecommender
from core.utils.text_processing import normalize_text

def _convert_to_decimal(obj):
    """
    Convierte números float a Decimal para DynamoDB.
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, list):
        return [_convert_to_decimal(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: _convert_to_decimal(v) for k, v in obj.items()}
    return obj

def _normalize_car_text(car: Dict[str, Any]) -> str:
    """
    Normaliza el texto de un auto para búsqueda semántica.
    Incluye información relevante como marca, modelo, versión, año, precio,
    kilometraje y características disponibles.
    
    Args:
        car: Diccionario con datos del auto
        
    Returns:
        Texto normalizado para embeddings
    """
    # Información básica
    basic_info = [
        car.get('make', ''),
        car.get('model', ''),
        car.get('version', ''),
        str(car.get('year', ''))
    ]
    
    # Información de precio y kilometraje
    price_info = []
    if 'price' in car:
        price = float(car['price'])
        if price >= 1_000_000:
            price_info.append(f"precio {price/1_000_000:.1f} millones")
        else:
            price_info.append(f"precio {price/1_000:.0f} mil")
            
    if 'km' in car:
        km = int(car['km'])
        if km >= 1_000_000:
            price_info.append(f"{km/1_000_000:.1f} millones de kilometros")
        else:
            price_info.append(f"{km/1_000:.0f} mil kilometros")
    
    # Dimensiones
    dimensions = []
    if car.get('largo'):
        dimensions.append(f"largo {car['largo']} metros")
    if car.get('ancho'):
        dimensions.append(f"ancho {car['ancho']} metros")
    if car.get('altura'):
        dimensions.append(f"altura {car['altura']} metros")
        
    # Características
    features = []
    if car.get('bluetooth'):
        features.append("bluetooth")
    if car.get('carPlay'):
        features.append("carplay")
        
    # Combinar toda la información
    all_info = basic_info + price_info + dimensions + features
    
    # Filtrar elementos vacíos y unir
    text = " ".join(filter(None, all_info))
    
    # Normalizar el texto final
    return normalize_text(text)

def _process_batch(
    recommender: CarRecommender,
    cars: List[Dict[str, Any]],
    existing_embeddings: Dict[str, Dict[str, Any]],
    update_threshold: str,
    now: datetime
) -> tuple[int, int, int]:
    """
    Procesa un lote de autos para actualizar sus embeddings.
    
    Args:
        recommender: Instancia de CarRecommender
        cars: Lista de autos a procesar
        existing_embeddings: Diccionario de embeddings existentes
        update_threshold: Umbral de actualización
        now: Timestamp actual
        
    Returns:
        Tupla con (total_processed, total_updated, total_errors)
    """
    total_processed = 0
    total_updated = 0
    total_errors = 0
    
    for car in cars:
        try:
            total_processed += 1
            stock_id = car["stockId"]
            
            # Normalizar texto del auto
            normalized_text = _normalize_car_text(car)
            print(f"[DEBUG] Texto normalizado para {stock_id}: {normalized_text}")
            
            # Verificar si necesita actualización
            needs_update = (
                stock_id not in existing_embeddings or
                existing_embeddings[stock_id]["lastUpdate"] < update_threshold or
                normalize_text(existing_embeddings[stock_id].get("text", "")) != normalized_text
            )
            
            if needs_update:
                print(f"[DEBUG] Actualizando embedding para {stock_id}...")
                
                # Obtener embedding
                embedding = recommender._get_embedding(normalized_text)
                if embedding:
                    print(f"[DEBUG] Embedding obtenido para {stock_id}, longitud: {len(embedding)}")
                    # Convertir embedding a Decimal
                    embedding_decimal = _convert_to_decimal(embedding)
                    print(f"[DEBUG] Embedding convertido a Decimal, longitud: {len(embedding_decimal)}")
                    
                    # Preparar item para DynamoDB
                    item = {
                        "stockId": stock_id,
                        "lastUpdate": now.isoformat(),
                        "embedding": embedding_decimal,
                        "text": normalized_text,
                        "original_text": f"{car['make']} {car['model']} {car.get('version', '')} {car['year']}"
                    }
                    
                    try:
                        # Guardar en DynamoDB
                        print(f"[DEBUG] Intentando guardar en tabla {recommender.embeddings_table}...")
                        response = recommender.embeddings_db.put_item(
                            Item=item,
                            ReturnConsumedCapacity='TOTAL'
                        )
                        print(f"[DEBUG] Respuesta de DynamoDB: {json.dumps(response, ensure_ascii=False)}")
                        total_updated += 1
                        print(f"[DEBUG] Embedding actualizado para {stock_id}")
                    except Exception as db_error:
                        print(f"[ERROR] Error al guardar en DynamoDB: {str(db_error)}")
                        print(f"[ERROR] Item que causó el error: {json.dumps({k: str(v) if k == 'embedding' else v for k, v in item.items()}, ensure_ascii=False)}")
                        total_errors += 1
                else:
                    print(f"[ERROR] No se pudo obtener embedding para {stock_id}")
                    total_errors += 1
            else:
                print(f"[DEBUG] Embedding actual para {stock_id}")
                
        except Exception as e:
            print(f"[ERROR] Error procesando auto {stock_id}: {str(e)}")
            total_errors += 1
            continue
            
    return total_processed, total_updated, total_errors

def handler(event, context):
    """
    Actualiza los embeddings de los autos en el catálogo.
    Se ejecuta periódicamente para mantener los embeddings actualizados.
    
    Args:
        event: Evento de CloudWatch Events/EventBridge
        context: Contexto de Lambda
    """
    try:
        print("[DEBUG] Iniciando actualización de embeddings...")
        
        # Inicializar servicios
        recommender = CarRecommender()
        
        # Obtener todos los autos del catálogo
        print("[DEBUG] Obteniendo catálogo de autos...")
        catalog_response = recommender.catalog_db.scan()
        cars = catalog_response.get("Items", [])
        print(f"[DEBUG] Se encontraron {len(cars)} autos en el catálogo")
        
        # Obtener embeddings existentes
        print("[DEBUG] Obteniendo embeddings existentes...")
        embeddings_response = recommender.embeddings_db.scan()
        existing_embeddings = {
            item["stockId"]: item 
            for item in embeddings_response.get("Items", [])
        }
        print(f"[DEBUG] Se encontraron {len(existing_embeddings)} embeddings existentes")
        
        # Verificar qué embeddings necesitan actualización
        now = datetime.utcnow()
        update_threshold = (now - timedelta(hours=24)).isoformat()
        
        # Procesar en lotes de 10 autos
        batch_size = 10
        total_processed = 0
        total_updated = 0
        total_errors = 0
        
        for i in range(0, len(cars), batch_size):
            batch = cars[i:i + batch_size]
            print(f"[DEBUG] Procesando lote {i//batch_size + 1} de {(len(cars) + batch_size - 1)//batch_size}")
            
            # Procesar lote
            processed, updated, errors = _process_batch(
                recommender,
                batch,
                existing_embeddings,
                update_threshold,
                now
            )
            
            total_processed += processed
            total_updated += updated
            total_errors += errors
            
            # Verificar tiempo restante
            if context and context.get_remaining_time_in_millis() < 60000:  # 1 minuto
                print("[WARN] Quedan menos de 60 segundos, deteniendo procesamiento...")
                break
        
        # Generar reporte
        report = {
            "timestamp": now.isoformat(),
            "total_processed": total_processed,
            "total_updated": total_updated,
            "total_errors": total_errors,
            "total_skipped": total_processed - total_updated - total_errors,
            "remaining_cars": len(cars) - total_processed
        }
        
        print(f"[DEBUG] Reporte final: {json.dumps(report, ensure_ascii=False)}")
        return report
        
    except Exception as e:
        print(f"[ERROR] Error en la actualización de embeddings: {str(e)}")
        import traceback
        print(f"[ERROR] Error traceback: {traceback.format_exc()}")
        raise 