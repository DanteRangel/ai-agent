import os
import json
import boto3
import math
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from decimal import Decimal
from openai import OpenAI
from core.utils.text_processing import normalize_text

def _convert_decimal_to_float(obj: Any) -> Any:
    """
    Convierte objetos Decimal a float para serialización JSON.
    
    Args:
        obj: Objeto a convertir
        
    Returns:
        Objeto convertido
    """
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, list):
        return [_convert_decimal_to_float(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: _convert_decimal_to_float(v) for k, v in obj.items()}
    return obj

class CarRecommender:
    """Servicio para recomendar autos basado en preferencias del usuario."""

    def __init__(self):
        """Inicializa el servicio con DynamoDB y OpenAI."""
        self.catalog_table = os.environ["CATALOG_TABLE"]
        self.embeddings_table = os.environ["EMBEDDINGS_TABLE"]
        
        # Configurar DynamoDB según el entorno
        if os.environ.get('STAGE') == 'dev':
            self.dynamodb = boto3.resource(
                'dynamodb',
                endpoint_url='http://localhost:8000',
                region_name='us-east-1',
                aws_access_key_id='dummy',
                aws_secret_access_key='dummy'
            )
        else:
            self.dynamodb = boto3.resource('dynamodb')
            
        self.catalog_db = self.dynamodb.Table(self.catalog_table)
        self.embeddings_db = self.dynamodb.Table(self.embeddings_table)
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    def _normalize_car_text(self, car: Dict[str, Any]) -> str:
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

    def _ensure_embeddings(self) -> None:
        """
        Verifica y actualiza los embeddings si es necesario.
        Los embeddings se actualizan solo si:
        1. No existen para algún auto
        2. Han pasado más de 24 horas desde la última actualización
        3. El texto normalizado ha cambiado
        """
        try:
            # Obtener todos los autos del catálogo
            catalog_response = self.catalog_db.scan()
            cars = catalog_response.get("Items", [])
            
            # Obtener embeddings existentes
            embeddings_response = self.embeddings_db.scan()
            existing_embeddings = {
                item["stockId"]: item 
                for item in embeddings_response.get("Items", [])
            }
            
            # Verificar qué embeddings necesitan actualización
            now = datetime.utcnow()
            update_threshold = (now - timedelta(hours=24)).isoformat()
            
            for car in cars:
                stock_id = car["stockId"]
                
                # Generar texto normalizado con toda la información relevante
                normalized_text = self._normalize_car_text(car)
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
                    embedding = self._get_embedding(normalized_text)
                    if embedding:
                        # Guardar en DynamoDB
                        item = {
                            "stockId": stock_id,
                            "lastUpdate": now.isoformat(),
                            "embedding": embedding,
                            "text": normalized_text,
                            "original_text": self._normalize_car_text(car)  # Guardar texto original también
                        }
                        
                        try:
                            self.embeddings_db.put_item(Item=item)
                            print(f"[DEBUG] Embedding actualizado para {stock_id}")
                        except Exception as db_error:
                            print(f"[ERROR] Error al guardar en DynamoDB: {str(db_error)}")
                            print(f"[ERROR] Item que causó el error: {json.dumps({k: str(v) if k == 'embedding' else v for k, v in item.items()}, ensure_ascii=False)}")
            
        except Exception as e:
            print(f"[ERROR] Error al verificar embeddings: {str(e)}")
            import traceback
            print(f"[ERROR] Error traceback: {traceback.format_exc()}")

    def _get_embedding(self, text: str) -> List[float]:
        """
        Obtiene el embedding de un texto usando OpenAI.
        
        Args:
            text: Texto a convertir en embedding
            
        Returns:
            Lista de floats representando el embedding
        """
        try:
            # Normalizar el texto antes de obtener el embedding
            normalized_text = normalize_text(text)
            print(f"[DEBUG] Texto normalizado para embedding: {normalized_text}")
            
            response = self.client.embeddings.create(
                input=normalized_text,
                model="text-embedding-ada-002"
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Error al obtener embedding: {str(e)}")
            return []

    def _get_catalog_embeddings(self) -> tuple[List[str], List[str], List[List[float]]]:
        """
        Obtiene los embeddings del catálogo desde DynamoDB.
        
        Returns:
            Tupla con (textos, stock_ids, embeddings)
        """
        try:
            response = self.embeddings_db.scan()
            items = response.get("Items", [])
            
            texts = []
            stock_ids = []
            embeddings = []
            
            for item in items:
                # Usar el texto normalizado para búsquedas
                texts.append(item["text"])  # Ya está normalizado
                stock_ids.append(item["stockId"])
                # Convertir embedding de Decimal a float
                embedding = [float(x) for x in item["embedding"]]
                embeddings.append(embedding)
            
            return texts, stock_ids, embeddings
            
        except Exception as e:
            print(f"Error al obtener embeddings del catálogo: {str(e)}")
            import traceback
            print(f"[ERROR] Error traceback: {traceback.format_exc()}")
            return [], [], []

    def _calculate_similarity(
        self, 
        query_embedding: List[float], 
        catalog_embeddings: List[List[float]]
    ) -> List[float]:
        """
        Calcula la similitud coseno entre el query y los embeddings del catálogo.
        
        Args:
            query_embedding: Embedding de la consulta
            catalog_embeddings: Lista de embeddings del catálogo
            
        Returns:
            Lista de scores de similitud
        """
        if not query_embedding or not catalog_embeddings:
            return []

        # Calcular la norma del query
        query_norm = math.sqrt(sum(x * x for x in query_embedding))
        if query_norm == 0:
            return []

        similarities = []
        for catalog_embedding in catalog_embeddings:
            # Calcular la norma del embedding del catálogo
            catalog_norm = math.sqrt(sum(x * x for x in catalog_embedding))
            if catalog_norm == 0:
                similarities.append(0)
                continue

            # Calcular el producto punto
            dot_product = sum(a * b for a, b in zip(query_embedding, catalog_embedding))
            
            # Calcular la similitud coseno
            similarity = dot_product / (query_norm * catalog_norm)
            similarities.append(similarity)

        return similarities

    def get_recommendations(
        self, 
        query: str, 
        max_recommendations: int = 10,
        min_similarity: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Obtiene recomendaciones de autos basadas en la consulta del usuario.
        
        Args:
            query: Texto de la consulta del usuario
            max_recommendations: Número máximo de recomendaciones
            min_similarity: Umbral mínimo de similitud
            
        Returns:
            Lista de autos recomendados
        """
        try:
            # Normalizar la consulta
            normalized_query = normalize_text(query)
            print(f"[DEBUG] Buscando recomendaciones para: {normalized_query}")
            print(f"[DEBUG] Tabla de catálogo: {self.catalog_table}")
            print(f"[DEBUG] Tabla de embeddings: {self.embeddings_table}")
            
            # Obtener embedding de la consulta
            print("[DEBUG] Obteniendo embedding de la consulta...")
            query_embedding = self._get_embedding(normalized_query)
            if not query_embedding:
                print("[ERROR] No se pudo obtener el embedding de la consulta")
                return []

            # Obtener embeddings del catálogo
            print("[DEBUG] Obteniendo embeddings del catálogo...")
            _, stock_ids, catalog_embeddings = self._get_catalog_embeddings()
            if not catalog_embeddings:
                print("[ERROR] No se encontraron embeddings en el catálogo")
                return []
            print(f"[DEBUG] Se encontraron {len(catalog_embeddings)} embeddings")

            # Calcular similitudes
            print("[DEBUG] Calculando similitudes...")
            similarities = self._calculate_similarity(query_embedding, catalog_embeddings)
            if not similarities:
                print("[ERROR] No se pudieron calcular similitudes")
                return []

            # Ordenar por similitud
            print("[DEBUG] Ordenando resultados por similitud...")
            stock_scores = list(zip(stock_ids, similarities))
            stock_scores.sort(key=lambda x: x[1], reverse=True)
            
            # Filtrar por similitud mínima y tomar los mejores
            top_stocks = [
                stock_id for stock_id, score in stock_scores 
                if score >= min_similarity
            ][:max_recommendations]
            
            if not top_stocks:
                print("[DEBUG] No se encontraron autos con similitud suficiente")
                return []
            
            # Obtener información actualizada del catálogo
            print("[DEBUG] Obteniendo información actualizada del catálogo...")
            recommendations = []
            for stock_id in top_stocks:
                try:
                    response = self.catalog_db.get_item(Key={"stockId": stock_id})
                    if "Item" in response:
                        car = response["Item"]
                        # Agregar score de similitud
                        car["similarity_score"] = next(
                            score for sid, score in stock_scores if sid == stock_id
                        )
                        recommendations.append(car)
                except Exception as e:
                    print(f"[ERROR] Error al obtener auto {stock_id}: {str(e)}")
                    continue
            
            # Convertir Decimal a float antes de devolver
            recommendations = _convert_decimal_to_float(recommendations)
            print(f"[DEBUG] Se encontraron {len(recommendations)} recomendaciones")
            return recommendations
            
        except Exception as e:
            print(f"[ERROR] Error al obtener recomendaciones: {str(e)}")
            import traceback
            print(f"[ERROR] Error traceback: {traceback.format_exc()}")
            return []

    def search_by_make_model(
        self,
        make: str = None,
        model: str = None,
        limit: int = 10,
        min_similarity: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Busca autos por marca y/o modelo usando embeddings para búsqueda semántica.
        
        Args:
            make: Marca del auto (opcional)
            model: Modelo del auto (opcional)
            limit: Límite de resultados
            min_similarity: Umbral mínimo de similitud
            
        Returns:
            Lista de autos encontrados
        """
        try:
            # Construir query de búsqueda
            search_terms = []
            if make:
                search_terms.append(make)
            if model:
                search_terms.append(model)
            
            if not search_terms:
                print("[ERROR] Se requiere al menos marca o modelo para buscar")
                return []
            
            # Construir texto de búsqueda
            search_text = " ".join(search_terms)
            print(f"[DEBUG] Buscando por texto: {search_text}")
            
            # Normalizar la consulta
            normalized_query = normalize_text(search_text)
            print(f"[DEBUG] Texto normalizado: {normalized_query}")
            
            # Obtener embedding de la consulta
            print("[DEBUG] Obteniendo embedding de la consulta...")
            query_embedding = self._get_embedding(normalized_query)
            if not query_embedding:
                print("[ERROR] No se pudo obtener el embedding de la consulta")
                return []

            # Obtener embeddings del catálogo
            print("[DEBUG] Obteniendo embeddings del catálogo...")
            _, stock_ids, catalog_embeddings = self._get_catalog_embeddings()
            if not catalog_embeddings:
                print("[ERROR] No se encontraron embeddings en el catálogo")
                return []
            print(f"[DEBUG] Se encontraron {len(catalog_embeddings)} embeddings")

            # Calcular similitudes
            print("[DEBUG] Calculando similitudes...")
            similarities = self._calculate_similarity(query_embedding, catalog_embeddings)
            if not similarities:
                print("[ERROR] No se pudieron calcular similitudes")
                return []

            # Ordenar por similitud
            print("[DEBUG] Ordenando resultados por similitud...")
            stock_scores = list(zip(stock_ids, similarities))
            stock_scores.sort(key=lambda x: x[1], reverse=True)
            
            # Filtrar por similitud mínima y tomar los mejores
            top_stocks = [
                stock_id for stock_id, score in stock_scores 
                if score >= min_similarity
            ][:limit]
            
            if not top_stocks:
                print("[DEBUG] No se encontraron autos con similitud suficiente")
                return []
            
            # Obtener información actualizada del catálogo
            print("[DEBUG] Obteniendo información actualizada del catálogo...")
            recommendations = []
            for stock_id in top_stocks:
                try:
                    response = self.catalog_db.get_item(Key={"stockId": stock_id})
                    if "Item" in response:
                        car = response["Item"]
                        # Agregar score de similitud
                        car["similarity_score"] = next(
                            score for sid, score in stock_scores if sid == stock_id
                        )
                        # Filtrar por marca/modelo si se especificó
                        if make and normalize_text(car.get("make", "")) != normalize_text(make):
                            continue
                        if model and normalize_text(car.get("model", "")) != normalize_text(model):
                            continue
                        recommendations.append(car)
                except Exception as e:
                    print(f"[ERROR] Error al obtener auto {stock_id}: {str(e)}")
                    continue
            
            # Convertir Decimal a float antes de devolver
            recommendations = _convert_decimal_to_float(recommendations)
            print(f"[DEBUG] Se encontraron {len(recommendations)} autos")
            return recommendations
            
        except Exception as e:
            print(f"[ERROR] Error al buscar por marca/modelo: {str(e)}")
            import traceback
            print(f"[ERROR] Error traceback: {traceback.format_exc()}")
            return []

    def search_by_price_range(
        self,
        min_price: float = None,
        max_price: float = None,
        year: int = None,
        limit: int = 10,
        min_similarity: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Busca autos dentro de un rango de precio usando embeddings para búsqueda semántica.
        
        Args:
            min_price: Precio mínimo (opcional)
            max_price: Precio máximo (opcional)
            year: Año específico (opcional)
            limit: Límite de resultados
            min_similarity: Umbral mínimo de similitud
            
        Returns:
            Lista de autos encontrados
        """
        try:
            # Construir query de búsqueda
            search_terms = []
            
            # Agregar términos de precio si existen
            if min_price is not None and max_price is not None:
                search_terms.append(f"precio entre {min_price} y {max_price}")
            elif min_price is not None:
                search_terms.append(f"precio mayor a {min_price}")
            elif max_price is not None:
                search_terms.append(f"precio menor a {max_price}")
            
            # Agregar año si existe
            if year is not None:
                search_terms.append(f"año {year}")
            
            if not search_terms:
                print("[ERROR] Se requiere al menos un criterio de búsqueda (precio o año)")
                return []
            
            # Construir texto de búsqueda
            search_text = " ".join(search_terms)
            print(f"[DEBUG] Buscando por texto: {search_text}")
            
            # Normalizar la consulta
            normalized_query = normalize_text(search_text)
            print(f"[DEBUG] Texto normalizado: {normalized_query}")
            
            # Obtener embedding de la consulta
            print("[DEBUG] Obteniendo embedding de la consulta...")
            query_embedding = self._get_embedding(normalized_query)
            if not query_embedding:
                print("[ERROR] No se pudo obtener el embedding de la consulta")
                return []

            # Obtener embeddings del catálogo
            print("[DEBUG] Obteniendo embeddings del catálogo...")
            _, stock_ids, catalog_embeddings = self._get_catalog_embeddings()
            if not catalog_embeddings:
                print("[ERROR] No se encontraron embeddings en el catálogo")
                return []
            print(f"[DEBUG] Se encontraron {len(catalog_embeddings)} embeddings")

            # Calcular similitudes
            print("[DEBUG] Calculando similitudes...")
            similarities = self._calculate_similarity(query_embedding, catalog_embeddings)
            if not similarities:
                print("[ERROR] No se pudieron calcular similitudes")
                return []

            # Ordenar por similitud
            print("[DEBUG] Ordenando resultados por similitud...")
            stock_scores = list(zip(stock_ids, similarities))
            stock_scores.sort(key=lambda x: x[1], reverse=True)
            
            # Filtrar por similitud mínima y tomar los mejores
            top_stocks = [
                stock_id for stock_id, score in stock_scores 
                if score >= min_similarity
            ][:limit]
            
            if not top_stocks:
                print("[DEBUG] No se encontraron autos con similitud suficiente")
                return []
            
            # Obtener información actualizada del catálogo
            print("[DEBUG] Obteniendo información actualizada del catálogo...")
            recommendations = []
            for stock_id in top_stocks:
                try:
                    response = self.catalog_db.get_item(Key={"stockId": stock_id})
                    if "Item" in response:
                        car = response["Item"]
                        # Agregar score de similitud
                        car["similarity_score"] = next(
                            score for sid, score in stock_scores if sid == stock_id
                        )
                        
                        # Filtrar por precio si se especificó
                        price = float(car.get("price", 0))
                        if min_price is not None and price < min_price:
                            continue
                        if max_price is not None and price > max_price:
                            continue
                            
                        # Filtrar por año si se especificó
                        if year is not None and car.get("year") != year:
                            continue
                            
                        recommendations.append(car)
                except Exception as e:
                    print(f"[ERROR] Error al obtener auto {stock_id}: {str(e)}")
                    continue
            
            # Convertir Decimal a float antes de devolver
            recommendations = _convert_decimal_to_float(recommendations)
            print(f"[DEBUG] Se encontraron {len(recommendations)} autos")
            return recommendations
            
        except Exception as e:
            print(f"[ERROR] Error al buscar por precio: {str(e)}")
            import traceback
            print(f"[ERROR] Error traceback: {traceback.format_exc()}")
            return []

    def get_financing_options(
        self, 
        car_price: float, 
        down_payment: float,
        interest_rate: float = 0.10,
        min_term: int = 36,
        max_term: int = 72
    ) -> List[Dict[str, Any]]:
        """
        Calcula opciones de financiamiento para un auto.
        
        Args:
            car_price: Precio del auto
            down_payment: Enganche
            interest_rate: Tasa de interés anual
            min_term: Plazo mínimo en meses
            max_term: Plazo máximo en meses
            
        Returns:
            Lista de opciones de financiamiento
        """
        try:
            loan_amount = car_price - down_payment
            if loan_amount <= 0:
                return []

            options = []
            for term in range(min_term, max_term + 12, 12):  # Incrementos de 12 meses
                monthly_rate = interest_rate / 12
                monthly_payment = (
                    loan_amount * 
                    (monthly_rate * (1 + monthly_rate) ** term) / 
                    ((1 + monthly_rate) ** term - 1)
                )
                
                total_payment = monthly_payment * term
                total_interest = total_payment - loan_amount

                options.append({
                    "term_months": term,
                    "term_years": term / 12,
                    "monthly_payment": round(monthly_payment, 2),
                    "total_payment": round(total_payment, 2),
                    "total_interest": round(total_interest, 2),
                    "down_payment": down_payment,
                    "loan_amount": loan_amount
                })

            return options

        except Exception as e:
            print(f"Error al calcular opciones de financiamiento: {str(e)}")
            return []

    def get_car_details(self, stock_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene todos los detalles disponibles de un auto específico.
        
        Args:
            stock_id: ID único del auto en el catálogo
            
        Returns:
            Diccionario con todos los detalles del auto o None si no se encuentra
        """
        try:
            # Buscar en el catálogo
            response = self.catalog_db.get_item(
                Key={"stockId": stock_id}
            )
            
            if "Item" not in response:
                print(f"[WARN] Auto no encontrado: {stock_id}")
                return None
                
            car = response["Item"]
            
            # Obtener embedding si existe
            embedding_response = self.embeddings_db.get_item(
                Key={"stockId": stock_id}
            )
            
            if "Item" in embedding_response:
                car["embedding"] = embedding_response["Item"].get("embedding")
                car["lastUpdate"] = embedding_response["Item"].get("lastUpdate")
            
            return car
            
        except Exception as e:
            print(f"[ERROR] Error obteniendo detalles del auto {stock_id}: {str(e)}")
            return None 