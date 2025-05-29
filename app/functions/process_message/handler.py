import os
import json
from typing import Dict, Any
from openai import OpenAI
from core.services.conversation import ConversationService, function_schemas, available_functions
from core.services.car_recommender import CarRecommender
from core.services.prompt_optimizer import PromptOptimizer

# Inicializar servicios
conversation_service = ConversationService()
car_recommender = CarRecommender()
prompt_optimizer = PromptOptimizer()
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def process_message(from_number: str, message_body: str) -> str:
    """
    Procesa el mensaje usando OpenAI y retorna la respuesta.
    
    Args:
        from_number: Número de WhatsApp del remitente
        message_body: Contenido del mensaje
        
    Returns:
        Respuesta del agente
    """
    try:
        print(f"[DEBUG] Iniciando procesamiento de mensaje de {from_number}: {message_body}")
        
        # Obtener contexto de conversación
        print("[DEBUG] Obteniendo contexto de conversación...")
        conversation_context = conversation_service.get_conversation_context(
            from_number,
            recent_messages=3
        ) or []  # Asegurar que sea una lista
        print(f"[DEBUG] Contexto obtenido: {json.dumps(conversation_context, ensure_ascii=False)}")
        
        # Preparar mensajes para OpenAI
        messages = [
            {"role": "system", "content": prompt_optimizer.system_prompt}
        ]
        
        # Agregar contexto si existe
        if conversation_context:
            messages.extend(conversation_context)
            
        # Agregar mensaje actual
        messages.append({"role": "user", "content": message_body})
        print(f"[DEBUG] Mensajes preparados para OpenAI: {json.dumps(messages, ensure_ascii=False)}")
        
        # Optimizar mensajes
        print("[DEBUG] Optimizando mensajes...")
        messages = prompt_optimizer.optimize_messages(
            messages,
            max_tokens=int(os.environ.get("MAX_TOKENS", "1000"))
        )
        
        # Obtener respuesta de OpenAI
        print("[DEBUG] Llamando a OpenAI...")
        response = client.chat.completions.create(
            model=os.environ.get("MODEL_NAME", "gpt-4-turbo-preview"),
            messages=messages,
            tools=[{"type": "function", "function": schema} for schema in function_schemas],
            tool_choice="auto",
            temperature=float(os.environ.get("TEMPERATURE", "0.7")),
            max_tokens=int(os.environ.get("MAX_TOKENS", "1000"))
        )
        
        response_message = response.choices[0].message
        print(f"[DEBUG] Respuesta inicial de OpenAI: {json.dumps(response_message.model_dump(), ensure_ascii=False)}")
        
        # Procesar tool calls si existen
        if response_message.tool_calls:
            print("[DEBUG] Procesando tool calls...")
            messages.append(response_message.model_dump())
            
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                print(f"[DEBUG] Ejecutando función {function_name} con args: {json.dumps(function_args, ensure_ascii=False)}")
                
                function_to_call = available_functions[function_name]
                function_response = function_to_call(**function_args)
                print(f"[DEBUG] Respuesta de función {function_name}: {json.dumps(function_response, ensure_ascii=False)}")
                
                if function_name in ["get_car_recommendations", "search_by_make_model", "search_by_price_range"]:
                    function_response = prompt_optimizer.compress_recommendations(function_response)
                    print(f"[DEBUG] Recomendaciones comprimidas: {json.dumps(function_response, ensure_ascii=False)}")
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": json.dumps(function_response)
                })
            
            print("[DEBUG] Llamando a OpenAI por segunda vez...")
            second_response = client.chat.completions.create(
                model=os.environ.get("MODEL_NAME", "gpt-4-turbo-preview"),
                messages=messages,
                temperature=float(os.environ.get("TEMPERATURE", "0.7")),
                max_tokens=int(os.environ.get("MAX_TOKENS", "1000"))
            )
            
            agent_message = second_response.choices[0].message.content
            print(f"[DEBUG] Respuesta final de OpenAI: {agent_message}")
        else:
            agent_message = response_message.content
            print(f"[DEBUG] Respuesta directa de OpenAI: {agent_message}")
        
        # Guardar la conversación
        print("[DEBUG] Guardando conversación...")
        conversation_service.save_message(
            whatsapp_number=from_number,
            user_message=message_body,
            agent_message=agent_message
        )
        print("[DEBUG] Conversación guardada exitosamente")
        
        return agent_message
        
    except Exception as e:
        print(f"[ERROR] Error en procesamiento de mensaje: {str(e)}")
        import traceback
        print(f"[ERROR] Error traceback: {traceback.format_exc()}")
        raise

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Manejador que procesa el mensaje usando OpenAI.
    
    Args:
        event: Evento del Step Function
        context: Contexto de Lambda
        
    Returns:
        Diccionario con la respuesta procesada
    """
    try:
        print(f"[DEBUG] Evento recibido: {json.dumps(event, ensure_ascii=False)}")
        from_number = event['from_number']
        message_body = event['message_body']
        
        print(f"[DEBUG] Procesando mensaje de {from_number}: {message_body}")
        agent_message = process_message(from_number, message_body)
        
        response = {
            'from_number': from_number,
            'message_body': message_body,
            'agent_message': agent_message
        }
        print(f"[DEBUG] Respuesta final: {json.dumps(response, ensure_ascii=False)}")
        return response
        
    except Exception as e:
        print(f"[ERROR] Error en el handler de procesamiento: {str(e)}")
        import traceback
        print(f"[ERROR] Error traceback: {traceback.format_exc()}")
        raise 