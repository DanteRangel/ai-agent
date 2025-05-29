import os
import json
from typing import Dict, Any
from twilio.rest import Client

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Envía la respuesta procesada al usuario a través de Twilio.
    
    Args:
        event: Evento del Step Function
        context: Contexto de Lambda
        
    Returns:
        Diccionario con el resultado del envío
    """
    try:
        from_number = event['from_number']
        agent_message = event['agent_message']
        
        # Enviar mensaje usando la API de Twilio
        client = Client(
            os.environ['TWILIO_ACCOUNT_SID'],
            os.environ['TWILIO_AUTH_TOKEN']
        )
        
        message = client.messages.create(
            from_=f"whatsapp:{os.environ['TWILIO_PHONE_NUMBER']}",
            to=from_number,
            body=agent_message
        )
        
        return {
            'status': 'success',
            'message_sid': message.sid,
            'from_number': from_number,
            'agent_message': agent_message
        }
        
    except Exception as e:
        print(f"Error al enviar respuesta: {str(e)}")
        import traceback
        print(f"Error traceback: {traceback.format_exc()}")
        raise 