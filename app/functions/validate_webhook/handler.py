import os
import json
from typing import Dict, Any
from twilio.request_validator import RequestValidator
from urllib.parse import parse_qsl

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Valida que la petición venga de Twilio.
    
    Args:
        event: Evento del Step Function
        context: Contexto de Lambda
        
    Returns:
        Diccionario con la información validada
        
    Raises:
        Exception: Si la validación falla
    """
    try:
        # Extraer información del evento
        headers = event.get('headers', {})
        body = event.get('body', {})
        
        # Obtener la firma de Twilio
        twilio_signature = headers.get('x-twilio-signature', '') or headers.get('X-Twilio-Signature', '')
        host = headers.get('host', '') or headers.get('Host', '')
        proto = headers.get('x-forwarded-proto', '') or headers.get('X-Forwarded-Proto', '')
        
        # Obtener el stage directamente del evento de API Gateway
        stage = event.get('requestContext', {}).get('stage', os.environ.get('STAGE', 'dev'))
        print(f"Stage from API Gateway: {stage}")
        
        if not twilio_signature:
            raise Exception("No Twilio signature found in headers")
            
        # Construir URL para validación
        url = f"{proto}://{host}/{stage}/webhook"
        
        # Convertir body a diccionario si es necesario
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                body = dict(parse_qsl(body))
        
        # Validar con Twilio
        validator = RequestValidator(os.environ['TWILIO_AUTH_TOKEN'])
        is_valid = validator.validate(
            url,
            body,
            twilio_signature
        )
        
        if not is_valid:
            raise Exception("Invalid Twilio signature")
        
        # Retornar información validada
        return {
            'from_number': body.get('From', ''),
            'message_body': body.get('Body', ''),
            'headers': headers,
            'body': body
        }
        
    except Exception as e:
        print(f"Error en validación de webhook: {str(e)}")
        import traceback
        print(f"Error traceback: {traceback.format_exc()}")
        raise 