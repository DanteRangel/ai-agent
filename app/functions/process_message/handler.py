import os
import json
from typing import Dict, Any
from openai import OpenAI
from core.services.conversation import ConversationService, function_schemas, available_functions
from core.services.car_recommender import CarRecommender
from core.services.prompt_optimizer import PromptOptimizer
from datetime import datetime

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
        print(f"[DEBUG] ===== INICIO DE PROCESAMIENTO =====")
        print(f"[DEBUG] Timestamp: {datetime.now().isoformat()}")
        print(f"[DEBUG] Número: {from_number}")
        print(f"[DEBUG] Mensaje: {message_body}")
        
        # Inicializar agent_message
        agent_message = ""
        
        # Obtener contexto de conversación
        print("[DEBUG] Obteniendo contexto de conversación...")
        conversation_context = conversation_service.get_conversation_context(
            from_number,
            recent_messages=3
        ) or []  # Asegurar que sea una lista
        
        print(f"[DEBUG] Número de mensajes en contexto: {len(conversation_context)}")
        for idx, msg in enumerate(conversation_context):
            print(f"[DEBUG] Mensaje {idx + 1}:")
            print(f"[DEBUG] - Rol: {msg['role']}")
            print(f"[DEBUG] - Contenido: {msg['content']}")
        
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
        print(f"[DEBUG] Total de mensajes para OpenAI: {len(messages)}")
        print(f"[DEBUG] Mensajes preparados para OpenAI: {json.dumps(messages, ensure_ascii=False)}")
        
        # Optimizar mensajes
        print("[DEBUG] Optimizando mensajes...")
        messages = prompt_optimizer.optimize_messages(
            messages,
            max_tokens=int(os.environ.get("MAX_TOKENS", "1000"))
        )
        print(f"[DEBUG] Total de mensajes después de optimización: {len(messages)}")
        
        # Obtener respuesta de OpenAI
        print("[DEBUG] Llamando a OpenAI...")
        print(f"[DEBUG] Modelo: {os.environ.get('MODEL_NAME', 'gpt-4-turbo-preview')}")
        print(f"[DEBUG] Temperature: {os.environ.get('TEMPERATURE', '0.7')}")
        print(f"[DEBUG] Max tokens: {os.environ.get('MAX_TOKENS', '1000')}")
        
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
        print(f"[DEBUG] Finish reason: {response.choices[0].finish_reason}")
        print(f"[DEBUG] Usage: {json.dumps(response.usage.model_dump(), ensure_ascii=False)}")
        
        # Analizar si se intentó usar alguna función
        if response_message.tool_calls:
            print("[DEBUG] OpenAI intentó usar funciones:")
            for tool_call in response_message.tool_calls:
                print(f"[DEBUG] - Función: {tool_call.function.name}")
                print(f"[DEBUG] - Argumentos: {tool_call.function.arguments}")
        else:
            print("[DEBUG] OpenAI no intentó usar ninguna función")
            print(f"[DEBUG] Contenido de la respuesta: {response_message.content}")
        
        # Procesar tool calls si existen
        if response_message.tool_calls:
            print("[DEBUG] Procesando tool calls...")
            print(f"[DEBUG] Número de tool calls: {len(response_message.tool_calls)}")
            messages.append(response_message.model_dump())
            
            for idx, tool_call in enumerate(response_message.tool_calls):
                print(f"[DEBUG] Procesando tool call {idx + 1} de {len(response_message.tool_calls)}")
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                print(f"[DEBUG] Ejecutando función {function_name} con args: {json.dumps(function_args, ensure_ascii=False)}")
                
                # Verificar si estamos en un estado apropiado para usar la función
                if function_name in ["search_by_make_model", "search_by_price_range", "get_car_recommendations"]:
                    if conversation_context[-1]["role"] == "assistant":
                        print(f"[DEBUG] ADVERTENCIA: Intento de usar {function_name} en estado {conversation_context[-1]['content']}")
                        print("[DEBUG] Ignorando función y continuando con conversación normal")
                        continue
                
                function_to_call = available_functions[function_name]
                function_response = function_to_call(**function_args)
                print(f"[DEBUG] Respuesta de función {function_name}: {json.dumps(function_response, ensure_ascii=False)}")
                
                if function_name in ["search_by_make_model", "search_by_price_range", "get_car_recommendations"]:
                    function_response = prompt_optimizer.compress_recommendations(function_response)
                    print(f"[DEBUG] Recomendaciones comprimidas: {json.dumps(function_response, ensure_ascii=False)}")
                elif function_name == "send_msat":
                    print("[DEBUG] Procesando respuesta de send_msat...")
                    success, msat_message = function_response
                    print(f"[DEBUG] Resultado send_msat - success: {success}, message: {msat_message}")
                    if success:
                        # Guardar MSAT en la conversación
                        print("[DEBUG] Guardando MSAT en la conversación...")
                        conversation_service.save_message(
                            whatsapp_number=from_number,
                            user_message=message_body,
                            agent_message=msat_message,
                            is_msat=True
                        )
                        print("[DEBUG] MSAT guardado exitosamente")
                        agent_message = msat_message
                        print("[DEBUG] Retornando mensaje MSAT directamente")
                        return agent_message
                    else:
                        function_response = "Lo siento, hubo un error al enviar la encuesta de satisfacción."
                elif function_name == "process_msat":
                    print("[DEBUG] Procesando respuesta de process_msat...")
                    # Asegurar que usamos el mismo número de teléfono que viene en el evento
                    function_args["from_number"] = from_number
                    function_response = function_to_call(**function_args)
                    success, rating, error_message = function_response
                    print(f"[DEBUG] Resultado process_msat - success: {success}, rating: {rating}, error: {error_message}")
                    
                    if not success:
                        agent_message = error_message
                        print("[DEBUG] Retornando mensaje de error de validación")
                        return ""
                    
                    # Guardar la respuesta del MSAT usando el mismo número de teléfono
                    success, thank_you = conversation_service.save_msat_response(from_number, rating)
                    if not success:
                        print("[DEBUG] Error al guardar respuesta MSAT")
                        return ""
                    
                    agent_message = thank_you
                    print("[DEBUG] Respuesta MSAT guardada exitosamente")
                    return agent_message
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": json.dumps(function_response)
                })
                print(f"[DEBUG] Tool call {idx + 1} procesado y agregado a mensajes")
            
            # Solo hacer segunda llamada a OpenAI si no es un MSAT
            if not any(tool_call.function.name in ["send_msat", "process_msat"] for tool_call in response_message.tool_calls):
                print("[DEBUG] Llamando a OpenAI por segunda vez...")
                print(f"[DEBUG] Total de mensajes para segunda llamada: {len(messages)}")
                second_response = client.chat.completions.create(
                    model=os.environ.get("MODEL_NAME", "gpt-4-turbo-preview"),
                    messages=messages,
                    temperature=float(os.environ.get("TEMPERATURE", "0.7")),
                    max_tokens=int(os.environ.get("MAX_TOKENS", "1000"))
                )
                
                agent_message = second_response.choices[0].message.content
                print(f"[DEBUG] Respuesta final de OpenAI: {agent_message}")
                print(f"[DEBUG] Finish reason (segunda llamada): {second_response.choices[0].finish_reason}")
                print(f"[DEBUG] Usage (segunda llamada): {json.dumps(second_response.usage.model_dump(), ensure_ascii=False)}")
                
                # Guardar conversación normal
                print("[DEBUG] Guardando conversación normal...")
                conversation_service.save_message(
                    whatsapp_number=from_number,
                    user_message=message_body,
                    agent_message=agent_message,
                    is_msat=False
                )
                print("[DEBUG] Conversación guardada exitosamente")
            else:
                print("[DEBUG] Omitiendo segunda llamada a OpenAI para MSAT")
        else:
            agent_message = response_message.content
            print(f"[DEBUG] Respuesta directa de OpenAI: {agent_message}")
            
            # Guardar conversación normal
            print("[DEBUG] Guardando conversación normal...")
            conversation_service.save_message(
                whatsapp_number=from_number,
                user_message=message_body,
                agent_message=agent_message,
                is_msat=False
            )
            print("[DEBUG] Conversación guardada exitosamente")
        
        print(f"[DEBUG] ===== FIN DE PROCESAMIENTO =====")
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