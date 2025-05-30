from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, ConfigDict
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.config import Settings

# Initialize password context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Initialize OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class Token(BaseModel):
    access_token: str
    token_type: str
    model_config = ConfigDict(from_attributes=True)

class TokenData(BaseModel):
    username: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Generate password hash."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
        
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        Settings.SECRET_KEY,
        algorithm=Settings.ALGORITHM
    )
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Get current user from JWT token."""
    try:
        payload = jwt.decode(
            token,
            Settings.SECRET_KEY,
            algorithms=[Settings.ALGORITHM]
        )
        username: str = payload.get("sub")
        if username is None:
            raise AuthenticationError("Invalid authentication credentials")
    except JWTError:
        raise AuthenticationError("Invalid authentication credentials")
        
    # Here you would typically fetch the user from your database
    # For now, we'll just return the username
    return {"username": username}

def verify_token(token: str) -> dict:
    """Verify JWT token and return payload."""
    try:
        payload = jwt.decode(
            token,
            Settings.SECRET_KEY,
            algorithms=[Settings.ALGORITHM]
        )
        return payload
    except JWTError:
        raise AuthenticationError("Invalid token")

def check_permissions(user: dict, required_permissions: list) -> bool:
    """Check if user has required permissions."""
    if not user.get("permissions"):
        return False
    return all(perm in user["permissions"] for perm in required_permissions)

def require_permissions(required_permissions: list):
    """Decorator to require specific permissions."""
    async def permission_checker(user: dict = Depends(get_current_user)):
        if not check_permissions(user, required_permissions):
            raise AuthorizationError("Insufficient permissions")
        return user
    return permission_checker 