import os
import json
import boto3
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
from core.services.car_recommender import CarRecommender
from core.services.prompt_optimizer import PromptOptimizer
from openai import OpenAI
from core.services.prospect_service import ProspectService

def _convert_decimals(obj):
    """
    Convierte objetos Decimal a int/float para serialización JSON.
    """
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    elif isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_decimals(i) for i in obj]
    return obj

class ConversationService:
    """Servicio para manejar el almacenamiento y recuperación de conversaciones de WhatsApp."""

    def __init__(self):
        """Inicializa el servicio con la tabla de DynamoDB."""
        self.table_name = f"kavak-ai-agent-conversations-{os.environ.get('STAGE', 'dev')}"
        
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
            
        self.table = self.dynamodb.Table(self.table_name)
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.summary_update_threshold = 5  # Número de mensajes antes de actualizar el resumen

    def _generate_summary(self, messages: List[Dict[str, str]], whatsapp_number: str) -> str:
        """
        Genera un resumen de la conversación usando GPT.
        
        Args:
            messages: Lista de mensajes a resumir
            whatsapp_number: Número de WhatsApp del usuario
            
        Returns:
            Resumen de la conversación que incluye el número de teléfono, intención del usuario,
            autos consultados y seleccionados
        """
        try:
            # Preparar prompt para resumen
            summary_prompt = [
                {"role": "system", "content": f"""Eres un asistente que resume conversaciones de manera concisa y estructurada. 
                Tu resumen DEBE incluir:
                1. El número de teléfono del usuario (whatsapp_number)
                2. La intención principal del usuario (qué está buscando)
                3. Las preferencias específicas mencionadas (marca, modelo, precio, etc.)
                4. Los autos consultados (todos los autos que el usuario ha visto o preguntado por ellos)
                5. Los autos seleccionados (autos que el usuario ha mostrado interés específico en comprar)
                6. Las decisiones o acuerdos tomados
                
                Formato del resumen:
                Número: [{whatsapp_number}]
                Intención: [descripción clara de lo que busca el usuario]
                Preferencias: [lista de preferencias mencionadas]
                Autos consultados: [lista de stockIds de autos que el usuario ha visto o preguntado]
                Autos seleccionados: [lista de stockIds de autos que el usuario ha mostrado interés en comprar]
                Estado: [decisiones o acuerdos tomados]
                
                Para identificar autos:
                - Busca patrones como "[stockId]" en los mensajes
                - Incluye TODOS los stockIds mencionados en "Autos consultados"
                - Solo incluye en "Autos seleccionados" aquellos donde el usuario expresó interés específico en comprar
                - Si no hay autos consultados o seleccionados, escribe "Ninguno" en esa sección
                
                Sé conciso pero incluye TODOS los elementos requeridos."""},
                {"role": "user", "content": f"""Genera un resumen estructurado de esta conversación:
                Número de WhatsApp: {whatsapp_number}
                Mensajes: {json.dumps(messages, ensure_ascii=False)}"""}
            ]
            
            # Obtener resumen de GPT
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",  # Modelo más económico para resúmenes
                messages=summary_prompt,
                max_tokens=250,  # Aumentado para dar espacio al formato estructurado
                temperature=0.3
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"Error al generar resumen: {str(e)}")
            return ""

    def _should_update_summary(self, conversation_id: str) -> bool:
        """
        Determina si se debe actualizar el resumen basado en el número de mensajes.
        
        Args:
            conversation_id: ID de la conversación
            
        Returns:
            True si se debe actualizar el resumen
        """
        try:
            # Obtener el último resumen
            response = self.table.query(
                IndexName="SummaryIndex",
                KeyConditionExpression="conversationId = :cid",
                ExpressionAttributeValues={":cid": conversation_id},
                Limit=1
            )
            
            items = response.get("Items", [])
            if not items:
                return True
                
            last_summary = items[0]
            message_count = last_summary.get("messageCount", 0)
            last_update = datetime.fromisoformat(last_summary.get("lastSummaryUpdate", "2000-01-01T00:00:00"))
            
            # Actualizar si han pasado más de X mensajes o más de 1 hora
            return (
                message_count >= self.summary_update_threshold or
                datetime.utcnow() - last_update > timedelta(hours=1)
            )
            
        except Exception as e:
            print(f"Error al verificar actualización de resumen: {str(e)}")
            return True

    def get_msat_status(self, whatsapp_number: str) -> Dict[str, Any]:
        """
        Obtiene el estado del MSAT para un usuario.
        
        Args:
            whatsapp_number: Número de WhatsApp del usuario
            
        Returns:
            Diccionario con el estado del MSAT
        """
        try:
            now = datetime.utcnow().isoformat()
            response = self.table.query(
                KeyConditionExpression="conversationId = :cid",
                FilterExpression="messageType = :type AND msatStatus = :status AND expiresAt > :now",
                ExpressionAttributeValues={
                    ":cid": whatsapp_number,
                    ":type": "msat",
                    ":status": "pending",
                    ":now": now
                },
                ScanIndexForward=False,
                Limit=1
            )
            
            if response.get("Items"):
                msat_item = response["Items"][0]
                return {
                    "has_pending_msat": True,
                    "msat_sent_time": msat_item.get("msatSentTime", ""),
                    "expires_at": msat_item.get("expiresAt", "")
                }
            return {
                "has_pending_msat": False,
                "msat_sent_time": "",
                "expires_at": ""
            }
            
        except Exception as e:
            print(f"[ERROR] Error al obtener estado MSAT: {str(e)}")
            return {
                "has_pending_msat": False,
                "msat_sent_time": "",
                "expires_at": ""
            }

    def get_conversation_context(
        self, 
        whatsapp_number: str,
        recent_messages: int = 3
    ) -> List[Dict[str, str]]:
        """
        Obtiene el contexto de la conversación (resumen + mensajes recientes).
        
        Args:
            whatsapp_number: Número de WhatsApp del usuario
            recent_messages: Número de mensajes recientes a incluir
            
        Returns:
            Lista de mensajes en formato para OpenAI
        """
        try:
            # Obtener estado del MSAT
            msat_status = self.get_msat_status(whatsapp_number)
            
            # Obtener todos los mensajes para verificar si es primer contacto
            all_messages = self.table.query(
                KeyConditionExpression="conversationId = :cid",
                ExpressionAttributeValues={":cid": whatsapp_number},
                ScanIndexForward=False
            )
            
            # Verificar si es primer contacto (no hay mensajes o solo hay un mensaje del usuario)
            is_first_message = (
                len(all_messages.get("Items", [])) == 0 or
                (len(all_messages.get("Items", [])) == 1 and 
                 "userMessage" in all_messages["Items"][0] and 
                 "agentMessage" not in all_messages["Items"][0])
            )
            
            # Obtener mensajes recientes para el contexto
            recent_messages_response = self.table.query(
                KeyConditionExpression="conversationId = :cid",
                ExpressionAttributeValues={":cid": whatsapp_number},
                ScanIndexForward=False,
                Limit=recent_messages
            )
            
            recent_context = []
            
            # Si es el primer mensaje, usar un prompt simple y directo
            if is_first_message:
                system_message = {
                    "role": "system",
                    "content": """Eres un asistente de ventas de Kavak. Tu objetivo es ayudar a los usuarios a encontrar y comprar el auto perfecto para ellos.

PRIMER CONTACTO:
- Saluda al usuario y preséntate como asistente de Kavak
- Menciona que es la plataforma líder de autos seminuevos
- Pregunta qué tipo de auto busca
- Usa un tono amigable y emojis apropiados

IMPORTANTE:
- NO repitas el saludo si el usuario ya respondió
- Si el usuario menciona una marca/modelo, busca DIRECTAMENTE usando search_by_make_model
- Si el usuario menciona un precio, busca usando search_by_price_range
- Si el usuario menciona características generales, usa get_car_recommendations"""
                }
                recent_context.append(system_message)
            else:
                # Obtener resumen si existe
                summary_response = self.table.query(
                    IndexName="SummaryIndex",
                    KeyConditionExpression="conversationId = :cid",
                    ExpressionAttributeValues={":cid": whatsapp_number},
                    Limit=1
                )
                
                summary_items = summary_response.get("Items", [])
                if summary_items and "summary" in summary_items[0]:
                    summary = summary_items[0]["summary"]
                    if summary:
                        system_message = f"""Eres un asistente de ventas de Kavak. Tu objetivo es ayudar a los usuarios a encontrar y comprar el auto perfecto para ellos.

CONTEXTO:
{summary}

INSTRUCCIONES:
1. Usa el resumen para mantener el contexto
2. NO preguntes información que ya está en el resumen
3. Si el usuario menciona una marca/modelo, busca DIRECTAMENTE
4. Si el usuario menciona un precio, busca por rango de precio
5. Si el usuario menciona características generales, usa recomendaciones
6. Al mencionar un auto, incluye su stockId entre corchetes [número]
7. Para agendar citas, verifica tener: nombre, fecha, hora y stockId"""
                        
                        recent_context.insert(0, {
                            "role": "system",
                            "content": system_message
                        })
            
            # Agregar mensajes recientes
            for item in reversed(recent_messages_response.get("Items", [])):
                if "userMessage" in item:
                    recent_context.append({
                        "role": "user",
                        "content": item["userMessage"]
                    })
                if "agentMessage" in item:
                    recent_context.append({
                        "role": "assistant",
                        "content": item["agentMessage"]
                    })
            
            return recent_context
            
        except Exception as e:
            print(f"[ERROR] Error al obtener contexto de conversación: {str(e)}")
            import traceback
            print(f"[ERROR] Error traceback: {traceback.format_exc()}")
            return []

    def save_message(
        self,
        whatsapp_number: str,
        user_message: str,
        agent_message: str,
        is_msat: bool = False
    ) -> bool:
        """
        Guarda un par de mensajes y actualiza el resumen si es necesario.
        
        Args:
            whatsapp_number: Número de WhatsApp del usuario
            user_message: Mensaje del usuario
            agent_message: Respuesta del agente
            is_msat: Indica si es un mensaje MSAT
            
        Returns:
            True si se guardó correctamente
        """
        try:
            timestamp = datetime.utcnow().isoformat()
            message_id = f"{timestamp}#{whatsapp_number}"
            item = {
                "conversationId": whatsapp_number,
                "messageId": message_id,
                "timestamp": timestamp,
                "messageType": "normal",
                "userMessage": user_message,
                "agentMessage": agent_message
            }
            
            if is_msat:
                print(f"[DEBUG] Guardando mensaje MSAT para {whatsapp_number}")
                item["messageType"] = "msat"
                item["msatStatus"] = "pending"
                item["msatRating"] = 0
                item["msatResponseTime"] = ""
                item["msatSentTime"] = timestamp
                item["expiresAt"] = (datetime.utcnow() + timedelta(hours=24)).isoformat()
                print(f"[DEBUG] Item MSAT a guardar: {json.dumps(item, ensure_ascii=False)}")
            
            # Guardar mensajes
            response = self.table.put_item(
                Item=item,
                ReturnValues="ALL_OLD"
            )
            print(f"[DEBUG] Respuesta de guardado: {json.dumps(response, ensure_ascii=False)}")
            
            # Verificar si se debe actualizar el resumen
            if self._should_update_summary(whatsapp_number):
                # Obtener últimos mensajes para el resumen
                history_response = self.table.query(
                    KeyConditionExpression="conversationId = :cid",
                    ExpressionAttributeValues={":cid": whatsapp_number},
                    ScanIndexForward=False,
                    Limit=10  # Últimos 10 mensajes para el resumen
                )
                
                messages = []
                for item in reversed(history_response.get("Items", [])):
                    if "userMessage" in item:
                        messages.append({
                            "role": "user",
                            "content": item["userMessage"]
                        })
                    if "agentMessage" in item:
                        messages.append({
                            "role": "assistant",
                            "content": item["agentMessage"]
                        })
                
                # Generar y guardar nuevo resumen
                summary = self._generate_summary(messages, whatsapp_number)
                if summary:
                    self.table.put_item(
                        Item={
                            "conversationId": whatsapp_number,
                            "messageId": "summary",
                            "timestamp": timestamp,
                            "summary": summary,
                            "lastSummaryUpdate": timestamp,
                            "messageCount": len(history_response.get("Items", []))
                        }
                    )
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Error al guardar mensaje: {str(e)}")
            import traceback
            print(f"[ERROR] Error traceback: {traceback.format_exc()}")
            return False

    def get_user_conversations(
        self, 
        user_id: str, 
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Obtiene las conversaciones recientes de un usuario web/móvil.
        No aplica para conversaciones de WhatsApp.
        
        Args:
            user_id: ID del usuario
            limit: Número máximo de conversaciones a recuperar
            
        Returns:
            Lista de conversaciones con sus últimos mensajes
        """
        try:
            # Solo buscar conversaciones que tengan userId
            response = self.table.query(
                IndexName="UserIdIndex",
                KeyConditionExpression="userId = :uid",
                FilterExpression="attribute_exists(userId)",
                ExpressionAttributeValues={":uid": user_id},
                ScanIndexForward=False,
                Limit=limit
            )

            conversations = []
            for item in response.get("Items", []):
                conversation = {
                    "conversationId": item["conversationId"],
                    "lastMessage": item.get("userMessage", ""),
                    "timestamp": item["timestamp"]
                }
                conversations.append(conversation)

            return conversations

        except Exception as e:
            print(f"Error al obtener conversaciones del usuario: {str(e)}")
            return []

    
    def send_msat_message(self, from_number: str) -> Tuple[bool, str]:
        """
        Envía el mensaje de MSAT al usuario y guarda su estado.
        
        Args:
            from_number: Número de WhatsApp del usuario
            
        Returns:
            Tupla con (éxito, mensaje MSAT)
        """
        try:
            print(f"[DEBUG] Enviando MSAT a {from_number}")
            
            # Generar mensaje MSAT usando formato de encuesta de WhatsApp
            msat_message = """¡Gracias por usar nuestro asistente! ¿Cómo calificarías tu experiencia?

Califica tu experiencia del 1 al 5, donde:
1 = Muy insatisfecho
2 = Insatisfecho
3 = Neutral
4 = Satisfecho
5 = Muy satisfecho

Responde solo con el número de tu calificación (1, 2, 3, 4 o 5)."""

            # Guardar el MSAT en la base de datos
            print("[DEBUG] Guardando MSAT en la base de datos...")
            success = self.save_message(
                whatsapp_number=from_number,
                user_message="",  # No hay mensaje del usuario al enviar MSAT
                agent_message=msat_message,
                is_msat=True
            )
            
            if not success:
                print("[ERROR] No se pudo guardar el MSAT en la base de datos")
                return False, ""
                
            print("[DEBUG] MSAT guardado exitosamente")
            return True, msat_message
            
        except Exception as e:
            print(f"[ERROR] Error al enviar MSAT: {str(e)}")
            import traceback
            print(f"[ERROR] Error traceback: {traceback.format_exc()}")
            return False, ""

    def process_msat_response(self, from_number: str, message: str) -> Tuple[bool, int, str]:
        """
        Verifica si la respuesta al MSAT es válida y extrae la calificación.
        
        Args:
            from_number: Número de WhatsApp del usuario
            message: Respuesta del MSAT
            
        Returns:
            Tupla con (éxito, calificación, mensaje de error)
        """
        try:
            print(f"[DEBUG] Verificando respuesta MSAT de {from_number}: {message}")
            
            # Extraer calificación
            clean_message = ''.join(c for c in message if c.isdigit())
            if not clean_message:
                print("[DEBUG] No se encontró un número en la respuesta")
                return False, 0, "Por favor, responde solo con un número del 1 al 5."
                
            rating = int(clean_message)
            if not 1 <= rating <= 5:
                print(f"[DEBUG] Calificación inválida: {rating}")
                return False, 0, "Por favor, responde con un número del 1 al 5."
            
            print(f"[DEBUG] Calificación válida extraída: {rating}")
            return True, rating, ""
            
        except Exception as e:
            print(f"[ERROR] Error al procesar respuesta MSAT: {str(e)}")
            import traceback
            print(f"[ERROR] Error traceback: {traceback.format_exc()}")
            return False, 0, "Hubo un error al procesar tu respuesta. Por favor, intenta de nuevo."

    def save_msat_response(self, from_number: str, rating: int) -> Tuple[bool, str]:
        """
        Guarda la respuesta del MSAT y actualiza su estado.
        
        Args:
            from_number: Número de WhatsApp del usuario
            rating: Calificación del usuario (1-5)
            
        Returns:
            Tupla con (éxito, mensaje de agradecimiento)
        """
        try:
            print(f"[DEBUG] Guardando respuesta MSAT de {from_number} con calificación {rating}")
            
            # Buscar MSAT pendiente
            print(f"[DEBUG] Buscando MSAT pendiente para {from_number}")
            
            # Primero, obtener todos los mensajes MSAT para diagnóstico
            all_msat = self.table.query(
                KeyConditionExpression="conversationId = :cid",
                FilterExpression="messageType = :type",
                ExpressionAttributeValues={
                    ":cid": from_number,
                    ":type": "msat"
                },
                ScanIndexForward=False
            )
            print(f"[DEBUG] Todos los MSAT encontrados: {json.dumps(_convert_decimals(all_msat.get('Items', [])), ensure_ascii=False)}")
            
            # Si encontramos MSATs, usar el más reciente que esté pendiente
            msat_items = all_msat.get("Items", [])
            if msat_items:
                # Filtrar manualmente los MSATs pendientes
                pending_msats = [
                    item for item in msat_items 
                    if item.get("msatStatus") == "pending" and 
                    datetime.fromisoformat(item["expiresAt"].replace('Z', '+00:00')) > datetime.utcnow()
                ]
                print(f"[DEBUG] MSATs pendientes encontrados: {json.dumps(_convert_decimals(pending_msats), ensure_ascii=False)}")
                
                if pending_msats:
                    msat_item = pending_msats[0]  # Tomar el más reciente
                    print(f"[DEBUG] Usando MSAT más reciente: {json.dumps(_convert_decimals(msat_item), ensure_ascii=False)}")
                    
                    # Verificar que tenemos los campos necesarios
                    if "messageId" not in msat_item:
                        print("[ERROR] MSAT item no tiene messageId")
                        return False, "Error interno: MSAT inválido"
                        
                    print(f"[DEBUG] Intentando actualizar MSAT con key: conversationId={from_number}, messageId={msat_item['messageId']}")
                    
                    try:
                        # Actualizar estado del MSAT usando la clave primaria completa
                        update_response = self.table.update_item(
                            Key={
                                "conversationId": from_number,
                                "messageId": msat_item["messageId"]
                            },
                            UpdateExpression="SET msatStatus = :status, msatRating = :rating, msatResponseTime = :time",
                            ExpressionAttributeValues={
                                ":status": "completed",
                                ":rating": rating,
                                ":time": datetime.utcnow().isoformat()
                            },
                            ReturnValues="ALL_NEW",
                            ConditionExpression="attribute_exists(messageId)"  # Asegurar que el item existe
                        )
                        
                        print(f"[DEBUG] MSAT actualizado exitosamente: {json.dumps(_convert_decimals(update_response.get('Attributes', {})), ensure_ascii=False)}")
                        
                        # Mensaje de agradecimiento personalizado según la calificación
                        if rating >= 4:
                            thank_you = "¡Gracias por tu excelente calificación! 🙏 Nos alegra que hayas tenido una gran experiencia con nuestro asistente."
                        elif rating == 3:
                            thank_you = "¡Gracias por tu retroalimentación! 🙏 Seguiremos trabajando para mejorar nuestro servicio."
                        else:
                            thank_you = "¡Gracias por tu retroalimentación! 🙏 Nos disculpamos por no haber cumplido tus expectativas. Tu opinión nos ayuda a mejorar."
                        
                        print(f"[DEBUG] Mensaje de agradecimiento: {thank_you}")
                        return True, thank_you
                        
                    except Exception as update_error:
                        print(f"[ERROR] Error al actualizar MSAT: {str(update_error)}")
                        import traceback
                        print(f"[ERROR] Error traceback: {traceback.format_exc()}")
                        return False, "Hubo un error al guardar tu calificación. Por favor, intenta de nuevo."
            
            print("[DEBUG] No se encontró ningún MSAT pendiente válido")
            return False, "Lo siento, no encontré una encuesta de satisfacción pendiente para responder."
            
        except Exception as e:
            print(f"[ERROR] Error al guardar respuesta MSAT: {str(e)}")
            import traceback
            print(f"[ERROR] Error traceback: {traceback.format_exc()}")
            return False, "Hubo un error al procesar tu respuesta. Por favor, intenta de nuevo."

# Inicializar servicios
conversation_service = ConversationService()
car_recommender = CarRecommender()
prompt_optimizer = PromptOptimizer()
prospect_service = ProspectService()

# Definición de herramientas disponibles
available_functions = {
    "search_by_make_model": car_recommender.search_by_make_model,
    "search_by_price_range": car_recommender.search_by_price_range,
    "get_car_recommendations": car_recommender.get_recommendations,
    "get_financing_options": car_recommender.get_financing_options,
    "get_car_details": car_recommender.get_car_details,
    "send_msat": conversation_service.send_msat_message,
    "process_msat": conversation_service.process_msat_response,
    "save_appointment": prospect_service.save_appointment,
    "get_prospect_appointments": prospect_service.get_prospect_appointments
}

# Definición de esquemas de funciones para OpenAI
function_schemas = [
    {
        "name": "search_by_make_model",
        "description": "PRIMERA OPCIÓN para buscar autos por marca y/o modelo. Usar esta función SIEMPRE que el usuario mencione una marca o modelo específico, incluso si también menciona otras características. Esta función es más precisa para búsquedas de marca/modelo porque usa embeddings especializados. IMPORTANTE: Al mostrar los resultados, DEBES usar EXACTAMENTE los mismos términos que vienen en el catálogo para marca, modelo, versión, etc. No modificar, abreviar o inventar nombres.",
        "parameters": {
            "type": "object",
            "properties": {
                "make": {
                    "type": "string",
                    "description": "Marca del auto (ej: 'toyota', 'honda', 'volkswagen'). IMPORTANTE: Usar exactamente el nombre de la marca como aparece en el catálogo."
                },
                "model": {
                    "type": "string",
                    "description": "Modelo del auto (ej: 'corolla', 'civic', 'golf'). IMPORTANTE: Usar exactamente el nombre del modelo como aparece en el catálogo."
                },
                "limit": {
                    "type": "integer",
                    "description": "Número máximo de resultados",
                    "default": 10
                },
                "min_similarity": {
                    "type": "number",
                    "description": "Umbral mínimo de similitud para los resultados (0.0 a 1.0)",
                    "default": 0.7
                }
            },
            "required": ["make"]
        }
    },
    {
        "name": "search_by_price_range",
        "description": "Busca autos dentro de un rango de precio y/o año. Usar esta función cuando el usuario busque específicamente por precio o año. También puedes buscar autos con características específicas como bluetooth o carplay.",
        "parameters": {
            "type": "object",
            "properties": {
                "min_price": {
                    "type": "number",
                    "description": "Precio mínimo en pesos (opcional)"
                },
                "max_price": {
                    "type": "number",
                    "description": "Precio máximo en pesos (opcional)"
                },
                "year": {
                    "type": "integer",
                    "description": "Año específico del auto (opcional)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Número máximo de resultados",
                    "default": 10
                },
                "min_similarity": {
                    "type": "number",
                    "description": "Umbral mínimo de similitud para los resultados (0.0 a 1.0)",
                    "default": 0.7
                }
            }
        }
    },
    {
        "name": "get_car_recommendations",
        "description": "ÚLTIMA OPCIÓN para buscar autos. Usar esta función SOLO cuando el usuario NO mencione una marca o modelo específico, y en su lugar busque por características generales (ej: 'un auto económico familiar', 'un SUV espacioso'). NO usar esta función si el usuario menciona una marca o modelo específico - en ese caso usar search_by_make_model. IMPORTANTE: Al mostrar los resultados, DEBES usar EXACTAMENTE los mismos términos que vienen en el catálogo para marca, modelo, versión, etc. No modificar, abreviar o inventar nombres.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Descripción de las preferencias del cliente (ej: 'un auto económico familiar'). IMPORTANTE: Solo mencionar características que estén en los datos del auto. NO usar esta función si el usuario menciona una marca o modelo específico."
                },
                "max_recommendations": {
                    "type": "integer",
                    "description": "Número máximo de recomendaciones a retornar",
                    "default": 3
                },
                "min_similarity": {
                    "type": "number",
                    "description": "Umbral mínimo de similitud para los resultados (0.0 a 1.0)",
                    "default": 0.7
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_financing_options",
        "description": "Calcula opciones de financiamiento para un auto",
        "parameters": {
            "type": "object",
            "properties": {
                "car_price": {
                    "type": "number",
                    "description": "Precio del auto en pesos"
                },
                "down_payment": {
                    "type": "number",
                    "description": "Enganche en pesos"
                },
                "interest_rate": {
                    "type": "number",
                    "description": "Tasa de interés anual (ej: 0.10 para 10%)",
                    "default": 0.10
                }
            },
            "required": ["car_price", "down_payment"]
        }
    },
    {
        "name": "get_car_details",
        "description": "Obtiene todos los detalles disponibles de un auto específico por su stockId. IMPORTANTE: El stockId debe ser exactamente el mismo que viene en los resultados de búsqueda o recomendaciones. No inventar o modificar el stockId.",
        "parameters": {
            "type": "object",
            "properties": {
                "stock_id": {
                    "type": "string",
                    "description": "ID único del auto en el catálogo. DEBE ser exactamente el mismo que viene en los resultados de búsqueda o recomendaciones. Ejemplo: si en los resultados aparece 'stockId': 'VW-GTI-2023-456', usar exactamente ese valor."
                }
            },
            "required": ["stock_id"]
        }
    },
    {
        "name": "send_msat",
        "description": "Envía el mensaje de MSAT (Mensaje de Satisfacción) al usuario cuando la conversación ha llegado a su fin. IMPORTANTE: El número de WhatsApp (from_number) debe ser el mismo número que está usando el usuario actual en la conversación. Este número se obtiene automáticamente del contexto de la conversación actual. Usar solo cuando el usuario ha resuelto su consulta principal y no requiere más asistencia.",
        "parameters": {
            "type": "object",
            "properties": {
                "from_number": {
                    "type": "string",
                    "description": "Número de WhatsApp del usuario actual. Este número se obtiene automáticamente del contexto de la conversación actual y debe ser el mismo número que está usando el usuario en este momento."
                }
            },
            "required": ["from_number"]
        }
    },
    {
        "name": "process_msat",
        "description": "Verifica si la respuesta del usuario al MSAT es válida (debe ser un número del 1 al 5). Esta función solo verifica la respuesta y extrae la calificación, no actualiza ningún estado.",
        "parameters": {
            "type": "object",
            "properties": {
                "from_number": {
                    "type": "string",
                    "description": "Número de WhatsApp del usuario actual"
                },
                "message": {
                    "type": "string",
                    "description": "Respuesta del usuario al MSAT (debe ser un número del 1 al 5)"
                }
            },
            "required": ["from_number", "message"]
        }
    },
    {
        "name": "save_msat_response",
        "description": "Guarda la respuesta del MSAT y actualiza su estado.",
        "parameters": {
            "type": "object",
            "properties": {
                "from_number": {
                    "type": "string",
                    "description": "Número de WhatsApp del usuario"
                },
                "rating": {
                    "type": "integer",
                    "description": "Calificación del usuario (1-5)"
                }
            },
            "required": ["from_number", "rating"]
        }
    },
    {
        "name": "save_appointment",
        "description": "Guarda una nueva cita para un prospecto. Esta función verifica automáticamente la disponibilidad antes de guardar la cita. Si no hay disponibilidad, retornará un mensaje de error. Si la cita se guarda exitosamente, retornará un mensaje de confirmación con los detalles de la cita.",
        "parameters": {
            "type": "object",
            "properties": {
                "whatsapp_number": {
                    "type": "string",
                    "description": "Número de WhatsApp del prospecto"
                },
                "prospect_name": {
                    "type": "string",
                    "description": "Nombre del prospecto"
                },
                "appointment_date": {
                    "type": "string",
                    "description": "Fecha de la cita en formato YYYY-MM-DD"
                },
                "appointment_time": {
                    "type": "string",
                    "description": "Hora de la cita en formato HH:MM"
                },
                "stock_id": {
                    "type": "string",
                    "description": "ID del auto en el catálogo (stockId)"
                },
                "status": {
                    "type": "string",
                    "description": "Estado de la cita (pending, confirmed, cancelled)",
                    "default": "pending"
                }
            },
            "required": ["whatsapp_number", "prospect_name", "appointment_date", "appointment_time", "stock_id"]
        }
    },
    {
        "name": "get_prospect_appointments",
        "description": "Obtiene las citas de un prospecto. Usar esta función cuando el usuario quiera ver sus citas programadas.",
        "parameters": {
            "type": "object",
            "properties": {
                "whatsapp_number": {
                    "type": "string",
                    "description": "Número de WhatsApp del prospecto"
                },
                "status": {
                    "type": "string",
                    "description": "Filtrar por estado de la cita (pending, confirmed, cancelled, completed)",
                    "enum": ["pending", "confirmed", "cancelled", "completed"]
                }
            },
            "required": ["whatsapp_number"]
        }
    }
]

