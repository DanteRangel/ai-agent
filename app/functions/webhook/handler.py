import os
import json
import boto3
from typing import Dict, Any
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse
from urllib.parse import parse_qsl
from core.utils.response import create_error_response

def validate_twilio_request(event):
    """Validate that the request is coming from Twilio."""
    try:
        # Get headers from the event
        headers = event.get('headers', {}) or {}
        
        # Get the Twilio signature
        twilio_signature = headers.get('x-twilio-signature', '') or headers.get('X-Twilio-Signature', '')
        host = headers.get('host', '') or headers.get('Host', '')
        proto = headers.get('x-forwarded-proto', '') or headers.get('X-Forwarded-Proto', '')
        
        # Obtener el stage directamente del evento de API Gateway
        stage = event.get('requestContext', {}).get('stage', os.environ.get('STAGE', 'dev'))
        print(f"Stage from API Gateway: {stage}")
        print(f"Proto: {proto}")
        print(f"Host: {host}")
        print(f"Twilio signature: {twilio_signature}")

        
        if not twilio_signature:
            print("ERROR: No Twilio signature found in headers")
            return False
            
        # Use the exact URL from Twilio console
        url = f"{proto}://{host}/{stage}/webhook"
        print(f"URL: {url}")
        # Get the raw body and parse it as form-urlencoded
        raw_body = event.get('body', '')
        print(f"Raw body: {raw_body}")
        if not raw_body:
            print("ERROR: Empty body received")
            return False
        
        # Parse the body as form-urlencoded parameters
        params = dict(parse_qsl(raw_body))
        
        # Get auth token
        auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
        if not auth_token:
            print("ERROR: TWILIO_AUTH_TOKEN not found in environment")
            return False
            
        # Create validator and validate
        validator = RequestValidator(auth_token)
        is_valid = validator.validate(url, params, twilio_signature)
        
        if not is_valid:
            print("WARNING: Twilio request validation failed")
        
        return is_valid
        
    except Exception as e:
        print(f"ERROR in validate_twilio_request: {str(e)}")
        return False

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Manejador del webhook de WhatsApp que inicia el Step Function.
    Solo se encarga de validar la petición y iniciar el proceso asíncrono.
    
    Args:
        event: Evento de API Gateway
        context: Contexto de Lambda
        
    Returns:
        Respuesta HTTP con TwiML vacío
    """
    try:
        # Validar que la petición venga de Twilio
        if not validate_twilio_request(event):
            return create_error_response(
                "Petición no autorizada",
                status_code=403,
                error_code="INVALID_SIGNATURE"
            )
        
        # Extraer información del mensaje
        body = event.get("body", "")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                body = dict(parse_qsl(body))

        from_number = body.get("From", "")
        message_body = body.get("Body", "")
        
        if not from_number or not message_body:
            return create_error_response(
                "Faltan campos requeridos",
                status_code=400,
                error_code="MISSING_FIELDS"
            )
        
        # Iniciar Step Function
        state_machine_arn = os.environ.get('STATE_MACHINE_ARN')
        if not state_machine_arn:
            raise ValueError("STATE_MACHINE_ARN no está configurado en las variables de entorno")
        
        sfn = boto3.client('stepfunctions')
        execution = sfn.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps({
                'headers': event.get('headers', {}),
                'body': body,
                'requestContext': event.get('requestContext', {})
            })
        )
        print(f"Step Function iniciada con execution ARN: {execution['executionArn']}")
        
        # Responder con TwiML vacío
        twiml = MessagingResponse()
        twiml_str = str(twiml)
        if not twiml_str.startswith('<?xml'):
            twiml_str = '<?xml version="1.0" encoding="UTF-8"?>' + twiml_str
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/xml",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Credentials": True
            },
            "body": twiml_str
        }
        
    except Exception as e:
        print(f"Error en el handler de webhook: {str(e)}")
        import traceback
        print(f"Error traceback: {traceback.format_exc()}")
        return create_error_response(
            "Error interno del servidor",
            status_code=500,
            error_code="INTERNAL_ERROR"
        ) 