import os
import json
from typing import Dict, Any
from twilio.rest import Client

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Envía un mensaje de error al usuario cuando algo falla en el proceso.
    
    Args:
        event: Evento del Step Function con el error
        context: Contexto de Lambda
        
    Returns:
        Diccionario con el resultado del envío
    """
    try:
        from_number = event['from_number']
        error_message = event.get('error', 'Lo siento, ha ocurrido un error al procesar tu mensaje. Por favor, intenta de nuevo más tarde.')
        
        # Enviar mensaje de error usando la API de Twilio
        client = Client(
            os.environ['TWILIO_ACCOUNT_SID'],
            os.environ['TWILIO_AUTH_TOKEN']
        )
        
        message = client.messages.create(
            from_=f"whatsapp:{os.environ['TWILIO_PHONE_NUMBER']}",
            to=from_number,
            body=error_message
        )
        
        return {
            'status': 'error_sent',
            'message_sid': message.sid,
            'from_number': from_number,
            'error_message': error_message
        }
        
    except Exception as e:
        print(f"Error al enviar mensaje de error: {str(e)}")
        import traceback
        print(f"Error traceback: {traceback.format_exc()}")
        # En este caso no propagamos el error para evitar un loop infinito
        return {
            'status': 'error_sending_error',
            'error': str(e)
        } 