from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import random
import asyncio
from typing import List, Dict
from pydantic import BaseModel, EmailStr, Field, validator
import re

from .database import get_db, engine
from .models import Base, User, EmailAccount, EmailHistory, OTPCode
from .auth import verify_password, get_password_hash, create_access_token, decode_token
from .email_service import EmailService
from .ai_service import AIService

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.user_connections: Dict[int, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.user_connections[user_id] = websocket

    def disconnect(self, websocket: WebSocket, user_id: int):
        self.active_connections.remove(websocket)
        if user_id in self.user_connections:
            del self.user_connections[user_id]

    async def send_personal_message(self, message: str, user_id: int):
        if user_id in self.user_connections:
            await self.user_connections[user_id].send_text(message)

manager = ConnectionManager()

# Email service instance
email_service = EmailService()
ai_service = AIService()

# Pydantic models
class UserSignup(BaseModel):
    username: str = Field(..., min_length=3)
    email: EmailStr
    phone: str
    password: str
    confirm_password: str
    dob: str
    captcha: bool = True

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        return v

class OTPSplitVerification(BaseModel):
    email: EmailStr
    phone: str
    otp_email_part: str
    otp_phone_part: str

class EmailRegistration(BaseModel):
    email_address: EmailStr
    phone_number: str

# Auth endpoints
@app.post("/api/auth/signup")
async def signup(user: UserSignup, db: Session = Depends(get_db)):
    # Check if user exists
    existing_user = db.query(User).filter(
        (User.email == user.email) | (User.username == user.username) | (User.phone == user.phone)
    ).first()
    
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    
    if user.password != user.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    
    if not user.captcha:
        raise HTTPException(status_code=400, detail="CAPTCHA verification required")
    
    # Create user
    hashed_password = get_password_hash(user.password)
    db_user = User(
        username=user.username,
        email=user.email,
        phone=user.phone,
        password_hash=hashed_password,
        dob=datetime.strptime(user.dob, "%Y-%m-%d")
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # Generate and send OTP
    otp_code = f"{random.randint(100000, 999999)}"
    otp = OTPCode(
        user_id=db_user.id,
        contact=user.email,
        code=otp_code,
        purpose="signup",
        expires_at=datetime.utcnow() + timedelta(minutes=5)
    )
    db.add(otp)
    db.commit()
    
    # Send OTP via email (implement actual email sending)
    print(f"OTP for {user.email}: {otp_code}")
    
    return {"message": "OTP sent", "user_id": db_user.id}

@app.post("/api/auth/verify-otp")
async def verify_otp(user_id: int, otp_code: str, db: Session = Depends(get_db)):
    otp_record = db.query(OTPCode).filter(
        OTPCode.user_id == user_id,
        OTPCode.code == otp_code,
        OTPCode.purpose == "signup",
        OTPCode.expires_at > datetime.utcnow()
    ).first()
    
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    
    db.delete(otp_record)
    db.commit()
    
    user = db.query(User).filter(User.id == user_id).first()
    token = create_access_token({"sub": str(user.id), "email": user.email})
    
    return {"token": token, "user": {"id": user.id, "username": user.username, "email": user.email}}

@app.post("/api/auth/login")
async def login(identifier: str, password: str, db: Session = Depends(get_db)):
    # Find user by email, username, or phone
    user = db.query(User).filter(
        (User.email == identifier) | (User.username == identifier) | (User.phone == identifier)
    ).first()
    
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Send OTP
    otp_code = f"{random.randint(100000, 999999)}"
    otp = OTPCode(
        user_id=user.id,
        contact=user.email,
        code=otp_code,
        purpose="login",
        expires_at=datetime.utcnow() + timedelta(minutes=5)
    )
    db.add(otp)
    db.commit()
    
    print(f"Login OTP for {user.email}: {otp_code}")
    
    return {"message": "OTP sent for verification", "user_id": user.id}

@app.post("/api/auth/login-verify")
async def login_verify(user_id: int, otp_code: str, db: Session = Depends(get_db)):
    otp_record = db.query(OTPCode).filter(
        OTPCode.user_id == user_id,
        OTPCode.code == otp_code,
        OTPCode.purpose == "login",
        OTPCode.expires_at > datetime.utcnow()
    ).first()
    
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    
    db.delete(otp_record)
    db.commit()
    
    user = db.query(User).filter(User.id == user_id).first()
    token = create_access_token({"sub": str(user.id), "email": user.email})
    
    return {"token": token, "user": {"id": user.id, "username": user.username, "email": user.email}}

@app.post("/api/auth/forgot-password")
async def forgot_password(email: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    otp_code = f"{random.randint(100000, 999999)}"
    otp = OTPCode(
        user_id=user.id,
        contact=email,
        code=otp_code,
        purpose="reset_password",
        expires_at=datetime.utcnow() + timedelta(minutes=5)
    )
    db.add(otp)
    db.commit()
    
    print(f"Password reset OTP for {email}: {otp_code}")
    
    return {"message": "OTP sent"}

@app.post("/api/auth/reset-password")
async def reset_password(email: str, otp_code: str, new_password: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    otp_record = db.query(OTPCode).filter(
        OTPCode.user_id == user.id,
        OTPCode.code == otp_code,
        OTPCode.purpose == "reset_password",
        OTPCode.expires_at > datetime.utcnow()
    ).first()
    
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    
    # Validate new password
    if len(new_password) < 8 or not re.search(r'[A-Z]', new_password) or not re.search(r'[0-9]', new_password) or not re.search(r'[!@#$%^&*(),.?":{}|<>]', new_password):
        raise HTTPException(status_code=400, detail="Password does not meet requirements")
    
    user.password_hash = get_password_hash(new_password)
    db.delete(otp_record)
    db.commit()
    
    return {"message": "Password reset successful"}

@app.post("/api/emails/register")
async def register_email(email_reg: EmailRegistration, user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if phone matches user's registered phone
    if email_reg.phone_number != user.phone:
        raise HTTPException(status_code=400, detail="Phone number must match registered phone")
    
    # Generate split OTP (3 digits to email, 3 digits to phone)
    email_part = f"{random.randint(100, 999)}"
    phone_part = f"{random.randint(100, 999)}"
    
    # Store split OTP in a temporary cache (using Redis in production)
    print(f"Split OTP - Email: {email_part}, Phone: {phone_part}")
    
    return {"message": "Split OTP sent", "email_part_length": 3, "phone_part_length": 3}

@app.post("/api/emails/verify-registration")
async def verify_registration(verification: OTPSplitVerification, user_id: int, db: Session = Depends(get_db)):
    # Verify split OTP (in production, check against stored values)
    # For demo, accept any valid 3-digit codes
    if not (verification.otp_email_part.isdigit() and len(verification.otp_email_part) == 3):
        raise HTTPException(status_code=400, detail="Invalid email OTP part")
    
    if not (verification.otp_phone_part.isdigit() and len(verification.otp_phone_part) == 3):
        raise HTTPException(status_code=400, detail="Invalid phone OTP part")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if email already registered
    existing_email = db.query(EmailAccount).filter(
        EmailAccount.user_id == user_id,
        EmailAccount.email_address == verification.email
    ).first()
    
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already registered for automation")
    
    # Register email for automation
    email_account = EmailAccount(
        user_id=user_id,
        email_address=verification.email,
        phone_verified=True,
        is_automated=True
    )
    db.add(email_account)
    db.commit()
    
    # Start email automation service
    asyncio.create_task(email_service.start_monitoring(verification.email, user_id, manager))
    
    return {"message": "Email automated successfully", "email_account_id": email_account.id}

@app.get("/api/emails/history")
async def get_email_history(user_id: int, page: int = 1, limit: int = 20, db: Session = Depends(get_db)):
    offset = (page - 1) * limit
    history = db.query(EmailHistory).filter(
        EmailHistory.user_id == user_id
    ).order_by(EmailHistory.timestamp.desc()).offset(offset).limit(limit).all()
    
    total = db.query(EmailHistory).filter(EmailHistory.user_id == user_id).count()
    
    return {
        "history": [
            {
                "id": h.id,
                "from_address": h.from_address,
                "subject": h.subject,
                "body": h.body[:200],
                "ai_analysis": h.ai_analysis,
                "action_taken": h.action_taken,
                "timestamp": h.timestamp.isoformat()
            } for h in history
        ],
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }

@app.websocket("/api/emails/live-activity")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await manager.connect(websocket, user_id)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)

@app.put("/api/emails/update/{email_id}")
async def update_email(email_id: int, is_automated: bool, user_id: int, db: Session = Depends(get_db)):
    email_account = db.query(EmailAccount).filter(
        EmailAccount.id == email_id,
        EmailAccount.user_id == user_id
    ).first()
    
    if not email_account:
        raise HTTPException(status_code=404, detail="Email account not found")
    
    email_account.is_automated = is_automated
    db.commit()
    
    return {"message": "Email automation updated"}

@app.delete("/api/emails/delete/{email_id}")
async def delete_email(email_id: int, user_id: int, db: Session = Depends(get_db)):
    email_account = db.query(EmailAccount).filter(
        EmailAccount.id == email_id,
        EmailAccount.user_id == user_id
    ).first()
    
    if not email_account:
        raise HTTPException(status_code=404, detail="Email account not found")
    
    db.delete(email_account)
    db.commit()
    
    return {"message": "Email account removed from automation"}

@app.post("/api/auth/logout")
async def logout():
    # JWT invalidation would require token blacklist with Redis
    return {"message": "Logged out successfully"}