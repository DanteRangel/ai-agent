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

def _normalize_car_text(car: Dict[str, Any], text_type: str = "full") -> str:
    """
    Normaliza el texto de un auto para búsqueda semántica.
    Puede generar texto para make, model o full description.
    
    Args:
        car: Diccionario con datos del auto
        text_type: Tipo de texto a generar ("make", "model", o "full")
        
    Returns:
        Texto normalizado para embeddings
    """
    if text_type == "make":
        return normalize_text(car.get('make', ''))
    elif text_type == "model":
        return normalize_text(f"{car.get('make', '')} {car.get('model', '')}")
    
    # Para text_type == "full", incluir toda la información
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
    """
    total_processed = 0
    total_updated = 0
    total_errors = 0
    total_skipped = 0  # Nuevo contador para registros saltados
    
    for car in cars:
        try:
            total_processed += 1
            stock_id = car["stockId"]
            
            # Generar textos normalizados para cada tipo
            make_text = _normalize_car_text(car, "make")
            model_text = _normalize_car_text(car, "model")
            full_text = _normalize_car_text(car, "full")
            
            print(f"[DEBUG] Procesando {stock_id}:")
            print(f"  - Make: {make_text}")
            print(f"  - Model: {model_text}")
            print(f"  - Full: {full_text}")
            
            # Verificar si necesita actualización
            if stock_id not in existing_embeddings:
                print(f"  [DEBUG] {stock_id} no existe en embeddings")
                needs_update = True
            elif existing_embeddings[stock_id]["lastUpdate"] < update_threshold:
                print(f"  [DEBUG] {stock_id} necesita actualización por tiempo")
                needs_update = True
            else:
                # Verificar cambios en textos
                existing_make = normalize_text(existing_embeddings[stock_id].get("make_text", ""))
                existing_model = normalize_text(existing_embeddings[stock_id].get("model_text", ""))
                existing_full = normalize_text(existing_embeddings[stock_id].get("full_text", ""))
                
                if existing_make != make_text:
                    print(f"  [DEBUG] {stock_id} cambió make_text: {existing_make} -> {make_text}")
                    needs_update = True
                elif existing_model != model_text:
                    print(f"  [DEBUG] {stock_id} cambió model_text: {existing_model} -> {model_text}")
                    needs_update = True
                elif existing_full != full_text:
                    print(f"  [DEBUG] {stock_id} cambió full_text: {existing_full} -> {full_text}")
                    needs_update = True
                else:
                    print(f"  [DEBUG] {stock_id} no necesita actualización")
                    needs_update = False
                    total_skipped += 1
            
            if needs_update:
                print(f"  [DEBUG] Obteniendo embeddings para {stock_id}...")
                
                # Obtener embeddings para cada tipo
                make_embedding = recommender._get_embedding(make_text)
                if not make_embedding:
                    print(f"  [ERROR] Falló embedding de make para {stock_id}")
                    total_errors += 1
                    continue
                    
                model_embedding = recommender._get_embedding(model_text)
                if not model_embedding:
                    print(f"  [ERROR] Falló embedding de model para {stock_id}")
                    total_errors += 1
                    continue
                    
                full_embedding = recommender._get_embedding(full_text)
                if not full_embedding:
                    print(f"  [ERROR] Falló embedding de full para {stock_id}")
                    total_errors += 1
                    continue
                
                print(f"  [DEBUG] Embeddings obtenidos para {stock_id}:")
                print(f"    - Make embedding longitud: {len(make_embedding)}")
                print(f"    - Model embedding longitud: {len(model_embedding)}")
                print(f"    - Full embedding longitud: {len(full_embedding)}")
                
                # Convertir embeddings a Decimal
                make_embedding_decimal = _convert_to_decimal(make_embedding)
                model_embedding_decimal = _convert_to_decimal(model_embedding)
                full_embedding_decimal = _convert_to_decimal(full_embedding)
                
                # Preparar item para DynamoDB
                item = {
                    "stockId": stock_id,
                    "lastUpdate": now.isoformat(),
                    "make_embedding": make_embedding_decimal,
                    "model_embedding": model_embedding_decimal,
                    "full_embedding": full_embedding_decimal,
                    "make_text": make_text,
                    "model_text": model_text,
                    "full_text": full_text
                }
                
                try:
                    # Guardar en DynamoDB
                    print(f"  [DEBUG] Guardando en tabla {recommender.embeddings_table}...")
                    response = recommender.embeddings_db.put_item(
                        Item=item,
                        ReturnConsumedCapacity='TOTAL'
                    )
                    print(f"  [DEBUG] Guardado exitoso: {json.dumps(response, ensure_ascii=False)}")
                    total_updated += 1
                except Exception as db_error:
                    print(f"  [ERROR] Error DynamoDB: {str(db_error)}")
                    print(f"  [ERROR] Item: {json.dumps({k: str(v) if 'embedding' in k else v for k, v in item.items()}, ensure_ascii=False)}")
                    total_errors += 1
                
        except Exception as e:
            print(f"[ERROR] Error general procesando {stock_id}: {str(e)}")
            total_errors += 1
            continue
            
    print(f"[DEBUG] Resumen del lote:")
    print(f"  - Procesados: {total_processed}")
    print(f"  - Actualizados: {total_updated}")
    print(f"  - Saltados: {total_skipped}")
    print(f"  - Errores: {total_errors}")
            
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
        print(f"[DEBUG] Umbral de actualización: {update_threshold}")
        
        # Procesar en lotes de 10 autos
        batch_size = 10
        total_processed = 0
        total_updated = 0
        total_errors = 0
        total_skipped = 0
        
        for i in range(0, len(cars), batch_size):
            batch = cars[i:i + batch_size]
            print(f"\n[DEBUG] Procesando lote {i//batch_size + 1} de {(len(cars) + batch_size - 1)//batch_size}")
            
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
            
        print("\n[DEBUG] Resumen final:")
        print(f"  - Total procesados: {total_processed}")
        print(f"  - Total actualizados: {total_updated}")
        print(f"  - Total saltados: {total_skipped}")
        print(f"  - Total errores: {total_errors}")
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Actualización de embeddings completada",
                "total_processed": total_processed,
                "total_updated": total_updated,
                "total_skipped": total_skipped,
                "total_errors": total_errors
            })
        }
        
    except Exception as e:
        print(f"[ERROR] Error en handler: {str(e)}")
        import traceback
        print(f"[ERROR] Error traceback: {traceback.format_exc()}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e)
            })
        } 