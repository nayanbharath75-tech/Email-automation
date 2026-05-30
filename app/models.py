from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    phone = Column(String(15), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    dob = Column(DateTime, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    email_accounts = relationship("EmailAccount", back_populates="user")
    email_history = relationship("EmailHistory", back_populates="user")
    otp_codes = relationship("OTPCode", back_populates="user")

class EmailAccount(Base):
    __tablename__ = "email_accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    email_address = Column(String(100), nullable=False)
    phone_verified = Column(Boolean, default=False)
    is_automated = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="email_accounts")
    email_history = relationship("EmailHistory", back_populates="email_account")

class EmailHistory(Base):
    __tablename__ = "email_history"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    email_account_id = Column(Integer, ForeignKey("email_accounts.id"), nullable=False)
    from_address = Column(String(100), nullable=False)
    subject = Column(String(500))
    body = Column(Text)
    ai_analysis = Column(Text)
    action_taken = Column(String(100))
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="email_history")
    email_account = relationship("EmailAccount", back_populates="email_history")

class OTPCode(Base):
    __tablename__ = "otp_codes"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    contact = Column(String(100), nullable=False)
    code = Column(String(6), nullable=False)
    purpose = Column(String(50), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="otp_codes")