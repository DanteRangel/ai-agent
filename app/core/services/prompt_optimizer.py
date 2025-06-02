import os
import json
from typing import List, Dict, Any, Optional
from openai import OpenAI

class PromptOptimizer:
    """Servicio para optimizar prompts y reducir el uso de tokens."""

    SYSTEM_PROMPT = """Eres un agente comercial de Kavak, plataforma líder de autos seminuevos en México.

INSTRUCCIONES CRÍTICAS:
1. RESPUESTA A INTERÉS EN COMPRAR:
   - Cuando el usuario diga "quiero un auto", "me gustaría comprar un auto", "busco un auto":
     * SIEMPRE responde: "¡Excelente! Para ayudarte mejor, necesito saber:
       1. ¿Qué tipo de auto prefieres? (SUV, sedan, hatchback, etc.)
       2. ¿Tienes alguna marca o modelo en mente?
       3. ¿Cuál es tu presupuesto aproximado?"
   - NUNCA respondas con saludos genéricos como "¿Cómo puedo ayudarte?"

2. IDENTIFICACIÓN DE AUTOS:
   - Cada auto tiene un stockId único
   - Formato: [stockId] - Marca Modelo Versión Año - Precio - Kilometraje
   - SIEMPRE incluye el stockId al mencionar un auto
   - NO inventes stockIds

3. BÚSQUEDA DE AUTOS:
   - NO uses funciones de búsqueda en saludos o conversaciones generales
   - Solo busca cuando tengas:
     * Marca/modelo específico
     * Rango de precio
     * Tipo de auto (SUV, sedan, etc.)

4. CITAS:
   - Horario: L-V 9:00-18:00, S 9:00-14:00
   - Verifica disponibilidad antes de agendar
   - Solicita nombre completo y confirma fecha/hora

5. MSAT:
   - Envía solo cuando la conversación llegue a su fin
   - No envíes si hay dudas pendientes
   - Procesa respuestas del 1 al 5

NO DEBES:
1. Inventar información sobre autos
2. Usar saludos genéricos cuando el usuario quiere comprar
3. Buscar autos sin información específica
4. Omitir el stockId al mencionar un auto
5. Agendar citas sin verificar disponibilidad
6. Enviar MSAT en momentos inapropiados

DEBES:
1. Hacer preguntas específicas sobre preferencias
2. Ser amable y profesional
3. Adaptar respuestas para WhatsApp (usar emojis)
4. Verificar disponibilidad antes de agendar citas
5. Seguir SIEMPRE las instrucciones de RESPUESTA A INTERÉS EN COMPRAR
"""

    SUMMARY_PROMPT = """Resume conversaciones enfocándote en:
1. Preferencias del cliente
2. Autos mencionados
3. Decisiones tomadas
4. Dudas pendientes
Máximo 2-3 oraciones."""

    def __init__(self):
        """Inicializa el servicio con OpenAI."""
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.system_prompt = self.SYSTEM_PROMPT
        self.summary_prompt = self.SUMMARY_PROMPT

    def get_optimized_system_prompt(self) -> str:
        """Retorna el prompt del sistema optimizado."""
        return self.system_prompt

    def get_optimized_summary_prompt(self) -> str:
        """Retorna el prompt de resumen optimizado."""
        return self.summary_prompt

    def optimize_messages(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1000
    ) -> List[Dict[str, str]]:
        """
        Optimiza una lista de mensajes para reducir tokens.
        
        Args:
            messages: Lista de mensajes a optimizar
            max_tokens: Número máximo de tokens permitidos
            
        Returns:
            Lista optimizada de mensajes
        """
        try:
            # Contar tokens aproximados
            total_tokens = sum(
                len(msg["content"].split()) * 1.3  # Estimación aproximada
                for msg in messages
            )
            
            if total_tokens <= max_tokens:
                return messages
            
            # Si excede el límite, optimizar
            optimized = []
            remaining_tokens = max_tokens
            
            # Siempre incluir el primer mensaje (system prompt)
            if messages:
                optimized.append(messages[0])
                remaining_tokens -= len(messages[0]["content"].split()) * 1.3
            
            # Incluir mensajes más recientes primero
            for msg in reversed(messages[1:]):
                msg_tokens = len(msg["content"].split()) * 1.3
                if msg_tokens <= remaining_tokens:
                    optimized.insert(1, msg)  # Insertar después del system prompt
                    remaining_tokens -= msg_tokens
                else:
                    break
            
            return optimized
            
        except Exception as e:
            print(f"Error al optimizar mensajes: {str(e)}")
            return messages

    def compress_car_info(self, car: Dict[str, Any]) -> str:
        """
        Comprime la información de un auto en un formato conciso.
        
        Args:
            car: Diccionario con información del auto
            
        Returns:
            String con información comprimida en formato: [stockId] - Marca Modelo Versión Año - Precio - Kilometraje
        """
        try:
            return (
                f"[{car['stockId']}] - {car['make']} {car['model']} {car.get('version', '')} "
                f"{car['year']} - ${car['price']:,} - {car['km']:,}km"
            )
        except Exception as e:
            print(f"Error al comprimir info del auto: {str(e)}")
            return str(car)

    def compress_recommendations(
        self,
        recommendations: List[Dict[str, Any]]
    ) -> str:
        """
        Comprime una lista de recomendaciones en un formato conciso.
        
        Args:
            recommendations: Lista de autos recomendados
            
        Returns:
            String con recomendaciones comprimidas
        """
        try:
            if not recommendations:
                return "No encontré autos que coincidan con tus preferencias."
            
            compressed = []
            for car in recommendations:
                compressed.append(self.compress_car_info(car))
            
            return "\n".join(compressed)
            
        except Exception as e:
            print(f"Error al comprimir recomendaciones: {str(e)}")
            return str(recommendations) 