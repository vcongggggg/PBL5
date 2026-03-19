from datetime import datetime, date

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Date,
    Boolean,
    Float,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    role = Column(String(20), default="admin")


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    plate_number = Column(String(20), unique=True, index=True, nullable=False)
    owner_name = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    note = Column(Text, nullable=True)

    subscriptions = relationship("Subscription", back_populates="vehicle")
    parking_sessions = relationship("ParkingSession", back_populates="vehicle")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    is_active = Column(Boolean, default=True)

    vehicle = relationship("Vehicle", back_populates="subscriptions")


class ParkingSession(Base):
    __tablename__ = "parking_sessions"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    plate_number = Column(String(20), index=True)
    direction = Column(String(10))  # in / out
    time_in = Column(DateTime, default=datetime.utcnow)
    time_out = Column(DateTime, nullable=True)
    fee = Column(Float, default=0)
    image_path = Column(String(255), nullable=True)

    vehicle = relationship("Vehicle", back_populates="parking_sessions")


class SystemConfig(Base):
    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(50), unique=True, index=True, nullable=False)
    value = Column(String(255), nullable=False)

