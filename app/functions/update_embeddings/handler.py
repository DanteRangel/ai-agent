import os
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any
from core.services.car_recommender import CarRecommender
from core.utils.text_processing import normalize_text
import time

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
    total_skipped = 0
    batch_start_time = time.time()
    
    for idx, car in enumerate(cars):
        item_start_time = time.time()
        try:
            total_processed += 1
            stock_id = car["stockId"]
            
            print(f"[DEBUG] [{datetime.now().isoformat()}] Procesando item {idx + 1}/{len(cars)} (stockId: {stock_id})")
            
            # Generar textos normalizados para cada tipo
            text_start = time.time()
            make_text = _normalize_car_text(car, "make")
            model_text = _normalize_car_text(car, "model")
            full_text = _normalize_car_text(car, "full")
            print(f"[DEBUG] Texto normalizado en {time.time() - text_start:.2f}s")
            
            # Verificar si necesita actualización
            check_start = time.time()
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
            print(f"[DEBUG] Verificación de actualización en {time.time() - check_start:.2f}s")
            
            if needs_update:
                print(f"  [DEBUG] Obteniendo embeddings para {stock_id}...")
                
                # Obtener embeddings para cada tipo
                embedding_start = time.time()
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
                print(f"[DEBUG] Embeddings generados en {time.time() - embedding_start:.2f}s")
                
                # Convertir embeddings a Decimal
                convert_start = time.time()
                make_embedding_decimal = _convert_to_decimal(make_embedding)
                model_embedding_decimal = _convert_to_decimal(model_embedding)
                full_embedding_decimal = _convert_to_decimal(full_embedding)
                print(f"[DEBUG] Conversión a Decimal en {time.time() - convert_start:.2f}s")
                
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
                    db_start = time.time()
                    print(f"  [DEBUG] {'Actualizando' if stock_id in existing_embeddings else 'Creando'} en tabla {recommender.embeddings_table}...")
                    
                    if stock_id in existing_embeddings:
                        # Actualizar item existente
                        update_expression = "SET lastUpdate = :lu, make_embedding = :me, model_embedding = :moe, full_embedding = :fe, make_text = :mt, model_text = :mot, full_text = :ft"
                        expression_values = {
                            ":lu": now.isoformat(),
                            ":me": make_embedding_decimal,
                            ":moe": model_embedding_decimal,
                            ":fe": full_embedding_decimal,
                            ":mt": make_text,
                            ":mot": model_text,
                            ":ft": full_text
                        }
                        
                        response = recommender.embeddings_db.update_item(
                            Key={"stockId": stock_id},
                            UpdateExpression=update_expression,
                            ExpressionAttributeValues=expression_values,
                            ReturnConsumedCapacity='TOTAL'
                        )
                    else:
                        # Crear nuevo item
                        response = recommender.embeddings_db.put_item(
                            Item=item,
                            ReturnConsumedCapacity='TOTAL'
                        )
                        
                    print(f"  [DEBUG] Operación exitosa en {time.time() - db_start:.2f}s: {json.dumps(response, ensure_ascii=False)}")
                    total_updated += 1
                except Exception as db_error:
                    print(f"  [ERROR] Error DynamoDB: {str(db_error)}")
                    print(f"  [ERROR] Item: {json.dumps({k: str(v) if 'embedding' in k else v for k, v in item.items()}, ensure_ascii=False)}")
                    total_errors += 1
                
        except Exception as e:
            print(f"[ERROR] Error general procesando {stock_id}: {str(e)}")
            total_errors += 1
            continue
            
        item_time = time.time() - item_start_time
        print(f"[DEBUG] Item {idx + 1} completado en {item_time:.2f}s")
            
    batch_time = time.time() - batch_start_time
    print(f"[DEBUG] Resumen del lote (completado en {batch_time:.2f}s):")
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
        start_time = time.time()
        print(f"[DEBUG] [{datetime.now().isoformat()}] Iniciando actualización de embeddings...")
        
        # Inicializar servicios
        init_start = time.time()
        recommender = CarRecommender()
        print(f"[DEBUG] Servicios inicializados en {time.time() - init_start:.2f}s")
        
        # Obtener todos los autos del catálogo
        catalog_start = time.time()
        print("[DEBUG] Obteniendo catálogo de autos...")
        catalog_response = recommender.catalog_db.scan()
        cars = catalog_response.get("Items", [])
        print(f"[DEBUG] Se encontraron {len(cars)} autos en el catálogo (en {time.time() - catalog_start:.2f}s)")
        
        # Obtener embeddings existentes
        embeddings_start = time.time()
        print("[DEBUG] Obteniendo embeddings existentes...")
        embeddings_response = recommender.embeddings_db.scan()
        existing_embeddings = {
            item["stockId"]: item 
            for item in embeddings_response.get("Items", [])
        }
        print(f"[DEBUG] Se encontraron {len(existing_embeddings)} embeddings existentes (en {time.time() - embeddings_start:.2f}s)")
        
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
            batch_start = time.time()
            batch = cars[i:i + batch_size]
            print(f"\n[DEBUG] [{datetime.now().isoformat()}] Procesando lote {i//batch_size + 1} de {(len(cars) + batch_size - 1)//batch_size}")
            
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
            
            batch_time = time.time() - batch_start
            print(f"[DEBUG] Lote {i//batch_size + 1} completado en {batch_time:.2f}s")
        
        total_time = time.time() - start_time
        print(f"\n[DEBUG] Resumen final (completado en {total_time:.2f}s):")
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
                "total_errors": total_errors,
                "execution_time_seconds": total_time
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