import re
import unicodedata
from typing import Optional

def normalize_text(text: str) -> str:
    """
    Normaliza un texto para búsqueda y comparación.
    
    Args:
        text: Texto a normalizar
        
    Returns:
        Texto normalizado
    """
    if not isinstance(text, str):
        return ""
        
    # Convertir a minúsculas
    text = text.lower()
    
    # Remover acentos
    text = unicodedata.normalize("NFKD", text)
    text = "".join([c for c in text if not unicodedata.combining(c)])
    
    # Remover caracteres especiales
    text = re.sub(r"[^a-z0-9\s]", "", text)
    
    # Remover espacios extra
    text = " ".join(text.split())
    
    return text

def extract_car_info(text: str) -> dict:
    """
    Extrae información de auto del texto usando expresiones regulares.
    
    Args:
        text: Texto a analizar
        
    Returns:
        Diccionario con información extraída
    """
    text = normalize_text(text)
    
    # Patrones comunes
    patterns = {
        "year": r"\b(19|20)\d{2}\b",  # Años entre 1900-2099
        "price": r"\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s*(?:k|m|pesos|mxn)?\b",
        "km": r"\b\d{1,3}(?:,\d{3})*\s*(?:km|kilometros)\b",
        "make": r"\b(?:volkswagen|toyota|honda|bmw|mercedes|audi|nissan|mazda|kia|ford|chevrolet)\b",
        "model": r"\b(?:golf|jetta|passat|corolla|camry|civic|cr-v|serie|clase|a3|a4|sentra|versa|mazda3|cx-5|rio|forte|fiesta|focus|spark|onix)\b"
    }
    
    info = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            value = match.group(0)
            
            # Limpiar y convertir valores
            if key == "year":
                info[key] = int(value)
            elif key == "price":
                # Convertir a número
                value = re.sub(r"[^\d.]", "", value)
                info[key] = float(value)
            elif key == "km":
                # Extraer solo números
                value = re.sub(r"[^\d]", "", value)
                info[key] = int(value)
            else:
                info[key] = value
    
    return info

def is_car_query(text: str) -> bool:
    """
    Determina si un texto es una consulta sobre autos.
    
    Args:
        text: Texto a analizar
        
    Returns:
        True si es una consulta de auto, False en caso contrario
    """
    text = normalize_text(text)
    
    # Palabras clave relacionadas con autos
    car_keywords = [
        "auto", "carro", "coche", "vehiculo", "marca", "modelo",
        "precio", "año", "kilometros", "km", "version", "transmision",
        "automatico", "manual", "gasolina", "diesel", "hibrido",
        "electrico", "suv", "sedan", "hatchback", "camioneta"
    ]
    
    # Verificar si contiene palabras clave
    return any(keyword in text for keyword in car_keywords)

def is_financing_query(text: str) -> bool:
    """
    Determina si un texto es una consulta sobre financiamiento.
    
    Args:
        text: Texto a analizar
        
    Returns:
        True si es una consulta de financiamiento, False en caso contrario
    """
    text = normalize_text(text)
    
    # Palabras clave relacionadas con financiamiento
    financing_keywords = [
        "financiamiento", "credito", "prestamo", "mensualidad",
        "enganche", "tasa", "interes", "plazo", "meses", "años",
        "pago", "mensual", "semanal", "quincenal", "anual"
    ]
    
    # Verificar si contiene palabras clave
    return any(keyword in text for keyword in financing_keywords) 