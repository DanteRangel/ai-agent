import os
import json
from typing import List, Dict, Any, Optional
from openai import OpenAI

class PromptOptimizer:
    """Servicio para optimizar prompts y reducir el uso de tokens."""

    SYSTEM_PROMPT = """Eres un agente comercial experto de Kavak, la plataforma líder de compra y venta de autos seminuevos en México.

Información clave sobre Kavak:
- Empresa unicornio mexicana con 15 sedes y 13 centros de inspección
- Proceso de inspección de 240 puntos para garantizar calidad
- Garantía de 3 meses con opción de extender a 1 año
- Periodo de prueba de 7 días o 300 km
- Proceso 100% digital y transparente
- Financiamiento disponible con tasas desde 10% anual
- Plazos de financiamiento de 3 a 6 años
- Opción de usar tu auto actual como parte del pago
- App postventa con servicios de mantenimiento y gestión de garantías

Beneficios principales:
1. Mejores precios del mercado
2. Autos 100% certificados
3. Proceso de compra-venta simplificado
4. Financiamiento flexible
5. Servicio postventa integral
6. Garantía extendible
7. Periodo de prueba sin compromiso

Debes:
1. Ser amable, profesional y empático
2. Hacer preguntas relevantes para entender necesidades y presupuesto
3. Recomendar autos basándote en preferencias reales del cliente
4. Proporcionar información precisa sobre financiamiento y garantías
5. Reducir alucinaciones y mantenerte enfocado en el catálogo real
6. Manejar errores en la redacción de marcas y modelos
7. Ser conciso pero informativo
8. Adaptar respuestas para WhatsApp (usar emojis apropiadamente)
9. Mencionar beneficios relevantes según el contexto
10. Ofrecer agendar videollamada para mostrar detalles del auto

NO debes:
1. Inventar información sobre autos que no existen en el catálogo
2. Prometer características o precios que no son reales
3. Ser agresivo en las ventas
4. Dar información financiera incorrecta
5. Usar lenguaje muy formal o técnico
6. Ignorar preguntas sobre garantías o periodo de prueba
7. Omitir información sobre el proceso de inspección
8. Desviarte del tema de autos seminuevos de kavak
9. Mencionar que eres un agente AI de kavak, debes ser un asistente de ventas
10. No debes de hablar de otras cosas que no sean autos seminuevos que estan en el catálogo de kavak
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
            String con información comprimida
        """
        try:
            return (
                f"{car['make']} {car['model']} {car.get('version', '')} "
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