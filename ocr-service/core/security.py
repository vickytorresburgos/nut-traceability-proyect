from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
import os

# Nombre del header que se buscará en las peticiones
API_KEY_NAME = "X-API-KEY"

# Configuración de FastAPI para detectar el header
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def validate_api_key(api_key: str = Security(api_key_header)):
    """
    Valida que el header X-API-KEY coincida con el valor en las variables de entorno.
    """
    expected_api_key = os.getenv("API_KEY")
    
    if not expected_api_key:
        return api_key

    if api_key == expected_api_key:
        return api_key
        
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="API Key inválida o faltante"
    )
