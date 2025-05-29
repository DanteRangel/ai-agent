import json
from typing import Any, Dict

def create_response(
    status_code: int,
    body: Any,
    headers: Dict[str, str] = None
) -> Dict[str, Any]:
    """
    Crea una respuesta HTTP para API Gateway.
    
    Args:
        status_code: Código de estado HTTP
        body: Cuerpo de la respuesta
        headers: Headers HTTP adicionales
        
    Returns:
        Diccionario con la respuesta formateada
    """
    default_headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Credentials": True
    }
    
    if headers:
        default_headers.update(headers)
    
    # Si el content type es XML, no codificar el body como JSON
    if headers and headers.get("Content-Type") == "application/xml":
        return {
            "statusCode": status_code,
            "headers": default_headers,
            "body": body
        }
    
    return {
        "statusCode": status_code,
        "headers": default_headers,
        "body": json.dumps(body, ensure_ascii=False)
    }

def create_error_response(
    message: str,
    status_code: int = 400,
    error_code: str = None
) -> Dict[str, Any]:
    """
    Crea una respuesta de error HTTP.
    
    Args:
        message: Mensaje de error
        status_code: Código de estado HTTP
        error_code: Código de error interno
        
    Returns:
        Diccionario con la respuesta de error formateada
    """
    body = {
        "error": {
            "message": message
        }
    }
    
    if error_code:
        body["error"]["code"] = error_code
    
    return create_response(status_code, body)

def create_success_response(
    data: Any,
    message: str = None
) -> Dict[str, Any]:
    """
    Crea una respuesta de éxito HTTP.
    
    Args:
        data: Datos de la respuesta
        message: Mensaje opcional
        
    Returns:
        Diccionario con la respuesta de éxito formateada
    """
    body = {"data": data}
    
    if message:
        body["message"] = message
    
    return create_response(200, body) 