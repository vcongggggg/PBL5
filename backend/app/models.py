from datetime import datetime

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


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    plate_number = Column(String(20), unique=True, index=True, nullable=False)
    owner_name = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    note = Column(Text, nullable=True)

    subscriptions = relationship("Subscription", back_populates="vehicle")
    parking_sessions = relationship("ParkingSession", back_populates="vehicle")
    rfid_cards = relationship("RFIDCard", back_populates="vehicle")


class MonthlyUser(Base):
    __tablename__ = "monthly_users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=True)
    address = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    subscriptions = relationship("Subscription", back_populates="monthly_user")
    rfid_cards = relationship("RFIDCard", back_populates="monthly_user")


class RFIDCard(Base):
    __tablename__ = "rfid_cards"

    id = Column(Integer, primary_key=True, index=True)
    card_uid = Column(String(100), unique=True, index=True, nullable=False)
    card_type = Column(String(20), nullable=False)  # monthly / guest
    is_active = Column(Boolean, default=True)
    issued_at = Column(DateTime, default=datetime.utcnow)
    expired_at = Column(DateTime, nullable=True)
    monthly_user_id = Column(Integer, ForeignKey("monthly_users.id"), nullable=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)

    monthly_user = relationship("MonthlyUser", back_populates="rfid_cards")
    vehicle = relationship("Vehicle", back_populates="rfid_cards")
    parking_sessions = relationship("ParkingSession", back_populates="rfid_card")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    monthly_user_id = Column(Integer, ForeignKey("monthly_users.id"), nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    registered_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    vehicle = relationship("Vehicle", back_populates="subscriptions")
    monthly_user = relationship("MonthlyUser", back_populates="subscriptions")


class ParkingSession(Base):
    __tablename__ = "parking_sessions"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    rfid_card_id = Column(Integer, ForeignKey("rfid_cards.id"), nullable=True)
    plate_number = Column(String(20), index=True)
    time_in = Column(DateTime, default=datetime.utcnow)
    time_out = Column(DateTime, nullable=True)
    fee = Column(Float, default=0)
    image_path = Column(String(255), nullable=True)
    gate_type = Column(String(10), default="entry")  # entry / exit
    trigger_type = Column(String(10), default="sensor")  # sensor / rfid / manual
    trigger_source_id = Column(String(50), nullable=True)
    rfid_tag = Column(String(100), nullable=True)
    plate_in = Column(String(20), nullable=True)
    plate_out = Column(String(20), nullable=True)
    match_status = Column(String(20), default="pending")  # pending / matched / mismatch
    confidence_in = Column(Float, nullable=True)
    confidence_out = Column(Float, nullable=True)
    rfid_card_type = Column(String(20), nullable=True)  # monthly / guest

    vehicle = relationship("Vehicle", back_populates="parking_sessions")
    rfid_card = relationship("RFIDCard", back_populates="parking_sessions")


class SystemConfig(Base):
    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(50), unique=True, index=True, nullable=False)
    value = Column(String(255), nullable=False)


class FireAlert(Base):
    __tablename__ = "fire_alerts"

    id = Column(Integer, primary_key=True, index=True)
    sensor_id = Column(String(50), nullable=False)
    level = Column(String(20), default="warning")
    message = Column(String(255), nullable=False)
    is_acknowledged = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

