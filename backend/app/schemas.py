from datetime import datetime, date
from typing import Optional, List

from pydantic import BaseModel, ConfigDict


class VehicleBase(BaseModel):
    plate_number: str
    owner_name: Optional[str] = None
    phone: Optional[str] = None
    note: Optional[str] = None


class VehicleCreate(VehicleBase):
    pass


class VehicleUpdate(BaseModel):
    owner_name: Optional[str] = None
    phone: Optional[str] = None
    note: Optional[str] = None


class Vehicle(VehicleBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class SubscriptionBase(BaseModel):
    vehicle_id: int
    monthly_user_id: int
    start_date: date
    end_date: date


class SubscriptionCreate(SubscriptionBase):
    pass


class Subscription(SubscriptionBase):
    id: int
    registered_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ParkingSessionBase(BaseModel):
    plate_number: str
    direction: str
    image_path: Optional[str] = None


class ParkingSessionCreate(ParkingSessionBase):
    vehicle_id: Optional[int] = None


class ParkingSession(ParkingSessionBase):
    id: int
    vehicle_id: Optional[int] = None
    rfid_card_id: Optional[int] = None
    time_in: datetime
    time_out: Optional[datetime] = None
    fee: float
    gate_type: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_source_id: Optional[str] = None
    rfid_tag: Optional[str] = None
    plate_in: Optional[str] = None
    plate_out: Optional[str] = None
    match_status: Optional[str] = None
    confidence_in: Optional[float] = None
    confidence_out: Optional[float] = None
    rfid_card_type: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class EspEventRequest(BaseModel):
    device_id: str
    event_type: str
    direction: str


class EspEventResponse(BaseModel):
    action: str  # open | close | ignore
    plate: str
    vehicle_type: str  # monthly | guest | unknown
    message: str


class ManualOpenRequest(BaseModel):
    device_id: str
    reason: str


class DashboardStats(BaseModel):
    total_in_bay: int
    today_total_in: int
    today_total_out: int
    today_revenue: float


class ParkingCheckoutRequest(BaseModel):
    plate_number: str


class ParkingCheckoutResponse(BaseModel):
    session: ParkingSession
    duration_minutes: int


class PlateRecognitionResult(BaseModel):
    plate: str
    confidence: float


class ParkingCheckinResponse(BaseModel):
    action: str
    plate: str
    confidence: float
    valid_plate: bool
    vehicle_type: str
    message: str
    session_id: Optional[int] = None


class GateTriggerRequest(BaseModel):
    gate_type: str  # entry | exit
    trigger_type: str  # sensor | rfid
    source_id: Optional[str] = None
    rfid_tag: Optional[str] = None


class GateTriggerResponse(BaseModel):
    status: str
    gate_type: str
    trigger_type: str
    source_id: Optional[str] = None
    rfid_tag: Optional[str] = None
    rfid_card_type: Optional[str] = None
    message: str


class GateScanResponse(BaseModel):
    action: str
    gate_type: str
    trigger_type: str
    rfid_card_type: Optional[str] = None
    plate_in: Optional[str] = None
    plate_out: Optional[str] = None
    recognized_plate: str
    confidence: float
    valid_plate: bool
    matched: bool
    session_id: Optional[int] = None
    duration_minutes: Optional[int] = None
    fee: Optional[float] = None
    message: str


class FireAlertCreate(BaseModel):
    sensor_id: str
    level: str = "warning"
    message: str


class FireAlert(BaseModel):
    id: int
    sensor_id: str
    level: str
    message: str
    is_acknowledged: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MonthlyUserBase(BaseModel):
    full_name: str
    phone: Optional[str] = None
    address: Optional[str] = None


class MonthlyUserCreate(MonthlyUserBase):
    pass


class MonthlyUser(MonthlyUserBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RFIDCardBase(BaseModel):
    card_uid: str
    card_type: str
    monthly_user_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    expired_at: Optional[datetime] = None


class RFIDCardCreate(RFIDCardBase):
    pass


class RFIDCard(RFIDCardBase):
    id: int
    is_active: bool
    issued_at: datetime

    model_config = ConfigDict(from_attributes=True)


