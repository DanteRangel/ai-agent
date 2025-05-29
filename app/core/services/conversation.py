import os
import json
import boto3
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from core.services.car_recommender import CarRecommender
from core.services.prompt_optimizer import PromptOptimizer
from openai import OpenAI

car_recommender = CarRecommender()
prompt_optimizer = PromptOptimizer()

# Definición de herramientas disponibles
available_functions = {
    "get_car_recommendations": car_recommender.get_recommendations,
    "search_by_make_model": car_recommender.search_by_make_model,
    "search_by_price_range": car_recommender.search_by_price_range,
    "get_financing_options": car_recommender.get_financing_options,
    "get_car_details": car_recommender.get_car_details
}

# Definición de esquemas de funciones para OpenAI
function_schemas = [
    {
        "name": "get_car_recommendations",
        "description": "Obtiene recomendaciones de autos basadas en una descripción textual. IMPORTANTE: Al mostrar los resultados, DEBES usar EXACTAMENTE los mismos términos que vienen en el catálogo para marca, modelo, versión, etc. No modificar, abreviar o inventar nombres. Por ejemplo, si en el catálogo aparece 'make: Volkswagen, model: Golf, version: GTI Performance', usar exactamente esos términos. Esto es crucial para que las búsquedas posteriores funcionen correctamente.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Descripción de las preferencias del cliente (ej: 'un auto económico familiar'). IMPORTANTE: Solo mencionar características que estén en los datos del auto."
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
        "name": "search_by_make_model",
        "description": "Busca autos por marca y modelo específicos",
        "parameters": {
            "type": "object",
            "properties": {
                "make": {
                    "type": "string",
                    "description": "Marca del auto (ej: 'toyota', 'honda')"
                },
                "model": {
                    "type": "string",
                    "description": "Modelo del auto (ej: 'corolla', 'civic')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Número máximo de resultados",
                    "default": 10
                }
            },
            "required": ["make"]
        }
    },
    {
        "name": "search_by_price_range",
        "description": "Busca autos dentro de un rango de precio y/o año. Puedes buscar por precio mínimo, máximo, o ambos, y opcionalmente por año. También puedes buscar autos con características específicas como bluetooth o carplay.",
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
    }
]

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

    def _generate_summary(self, messages: List[Dict[str, str]]) -> str:
        """
        Genera un resumen de la conversación usando GPT.
        
        Args:
            messages: Lista de mensajes a resumir
            
        Returns:
            Resumen de la conversación
        """
        try:
            # Preparar prompt para resumen
            summary_prompt = [
                {"role": "system", "content": "Eres un asistente que resume conversaciones de manera concisa. Enfócate en las preferencias del cliente, autos mencionados y decisiones tomadas."},
                {"role": "user", "content": f"Resume esta conversación de manera concisa:\n{json.dumps(messages, ensure_ascii=False)}"}
            ]
            
            # Obtener resumen de GPT
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",  # Modelo más económico para resúmenes
                messages=summary_prompt,
                max_tokens=150,
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
            # Obtener mensajes recientes
            response = self.table.query(
                KeyConditionExpression="conversationId = :cid",
                ExpressionAttributeValues={":cid": whatsapp_number},
                ScanIndexForward=False,  # Orden descendente
                Limit=recent_messages
            )
            
            recent_context = []
            for item in reversed(response.get("Items", [])):
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
                    recent_context.insert(0, {
                        "role": "system",
                        "content": f"Resumen de la conversación anterior: {summary}"
                    })
            
            return recent_context
            
        except Exception as e:
            print(f"Error al obtener contexto de conversación: {str(e)}")
            return []

    def get_conversation_history(
        self, 
        whatsapp_number: str, 
        limit: int = 10
    ) -> List[Dict[str, str]]:
        """
        Obtiene el historial de conversación para un número de WhatsApp.
        
        Args:
            whatsapp_number: Número de WhatsApp del usuario
            limit: Número máximo de mensajes a recuperar
            
        Returns:
            Lista de mensajes en formato para OpenAI
        """
        try:
            response = self.table.query(
                KeyConditionExpression="conversationId = :cid",
                ExpressionAttributeValues={":cid": whatsapp_number},
                ScanIndexForward=False,  # Orden descendente (más recientes primero)
                Limit=limit
            )

            # Convertir los mensajes al formato de OpenAI
            messages = []
            for item in reversed(response.get("Items", [])):  # Revertir para orden cronológico
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

            return messages

        except Exception as e:
            print(f"Error al obtener historial de conversación: {str(e)}")
            return []

    def save_message(
        self,
        whatsapp_number: str,
        user_message: str,
        agent_message: str
    ) -> bool:
        """
        Guarda un par de mensajes y actualiza el resumen si es necesario.
        
        Args:
            whatsapp_number: Número de WhatsApp del usuario
            user_message: Mensaje del usuario
            agent_message: Respuesta del agente
            
        Returns:
            True si se guardó correctamente
        """
        try:
            timestamp = datetime.utcnow().isoformat()
            message_id = f"{timestamp}#{whatsapp_number}"
            
            # Guardar mensajes
            self.table.put_item(
                Item={
                    "conversationId": whatsapp_number,
                    "messageId": message_id,
                    "timestamp": timestamp,
                    "userMessage": user_message,
                    "agentMessage": agent_message
                }
            )
            
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
                summary = self._generate_summary(messages)
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
            print(f"Error al guardar mensaje: {str(e)}")
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
        