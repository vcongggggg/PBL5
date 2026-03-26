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
    start_date: date
    end_date: date


class SubscriptionCreate(SubscriptionBase):
    pass


class Subscription(SubscriptionBase):
    id: int
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
    time_in: datetime
    time_out: Optional[datetime] = None
    fee: float

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


