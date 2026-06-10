from fastapi import Security, HTTPException, status, Depends
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
import os
from sqlalchemy.orm import Session
from database import get_db, User
from core.config import settings

# Contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Nombre del header que se buscará en las peticiones (Legacy API Key)
API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    # Bcrypt tiene un límite de 72 bytes. Truncamos para evitar errores del backend.
    if len(password) > 72:
        password = password[:72]
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Usuario inactivo")
    return user

def validate_api_key(api_key: str = Security(api_key_header)):
    """
    Valida que el header X-API-KEY coincida con el valor en las variables de entorno.
    (Mantenido por compatibilidad legacy si es necesario, pero se prefiere JWT)
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
