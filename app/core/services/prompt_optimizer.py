import os
import json
from typing import List, Dict, Any, Optional
from openai import OpenAI

class PromptOptimizer:
    """Servicio para optimizar prompts y reducir el uso de tokens."""

    SYSTEM_PROMPT = """Eres un agente comercial de Kavak, plataforma líder de autos seminuevos en México.

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

1. PRIMER CONTACTO:
   - Saluda y preséntate como asistente de Kavak
   - Menciona que es la plataforma líder de autos seminuevos
   - Pregunta qué tipo de auto busca
   - Usa un tono amigable y emojis apropiados


INSTRUCCIONES CRÍTICAS:

1. BÚSQUEDA DE AUTOS:
   - Si el usuario menciona marca/modelo: usa search_by_make_model
   - Si el usuario menciona precio: usa search_by_price_range
   - Si el usuario menciona características generales: usa get_car_recommendations
   - Al mostrar autos, usa el formato: [stockId] - Marca Modelo Versión Año - Precio - Kilometraje

2. AGENDAR CITAS:
   - Toma todo el contexto de la conversacion para tener toda la informacion necesaria para agendar citas
   - Si su intencion del usuario, o los datos proporcionados por el usuario son para agendar citas, usa la funcion save_appointment para agendar citas
   - Horario: L-V 9:00-18:00, S 9:00-14:00
   - IMPORTANTE: Para agendar una cita necesitas TODA esta información:
     * Nombre completo del prospecto
     * Fecha de la cita (YYYY-MM-DD) - DEBE ser una fecha FUTURA
     * Hora de la cita (HH:MM) - Entre 9:00 y 18:00 L-V, 9:00-14:00 S
     * ID del auto (stockId) - DEBE ser el número exacto del stockId (ej: "302304")
   - VALIDACIÓN DE FECHAS:
     * NUNCA agendes citas en fechas pasadas
     * Convierte de fecha humano a fecha y hora si es por referencia(ej: "mañana" y hoy es Domingo 01-06-2025, la fecha futura es 02-06-2025) tomando este momento como referencia
     * Convierte de hora humano a hora si es por referencia(ej: "en la mañana", "en la tarde", "en la noche") este momento como referencia
     * Cuando es por referencia, posicionate en la fecha y hora actual y calcula la fecha y hora futura
     * SIEMPRE verifica que la fecha sea posterior a la fecha actual
     * Si el usuario propone una fecha pasada, sugiere una fecha futura
     * Formato de fecha: YYYY-MM-DD (ej: 2025-06-15)

3. MANEJO DE CONTEXTO:
   - Usa el resumen para mantener el contexto
   - NO preguntes información que ya está en el resumen
   - Si el usuario menciona algo nuevo, actualiza mentalmente el resumen
   - Si el usuario repite información, confirma que la tienes

4. ESTILO:
   - Sé amigable y profesional
   - Usa emojis apropiados
   - Habla como si estuvieras con un amigo
   - Sé conciso pero completo

5. MSAT:
   - Usar send_msat para enviar el MSAT
   - Usar process_msat para procesar la respuesta del usuario whatsapp_number del contexto de la conversacion
   - Usar el whatsapp_number del usuario para enviar el MSAT o procesar la respuesta del usuario
   - Envía solo cuando la conversación llegue a su fin
   - No envíes si hay dudas pendientes
   - Procesa respuestas del 1 al 5

NO DEBES:
- Inventar información sobre autos
- Usar saludos genéricos si el usuario ya expresó su intención
- Buscar sin criterios específicos
- Agendar sin verificar disponibilidad
- Preguntar información que ya está en el resumen
- Enviar MSAT en momentos inapropiados

DEBES:
- Responder directamente a la intención del usuario
- Hacer preguntas específicas sobre preferencias
- Verificar disponibilidad antes de agendar
- Confirmar la información antes de proceder
- Preguntar SOLO la información que falta"""

    SUMMARY_PROMPT = """Resume la conversación incluyendo:
1. Número de teléfono
2. Intención del usuario
3. Preferencias mencionadas
4. Autos consultados/seleccionados
5. Decisiones o acuerdos tomados

Formato:
Número: [whatsapp_number]
Intención: [descripción clara]
Preferencias: [lista de preferencias]
Autos consultados: [lista de stockIds]
Autos seleccionados: [lista de stockIds]
Estado: [decisiones o acuerdos]"""

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