from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, time
from enum import Enum

class CallStep(str, Enum):
    GREETING = "greeting"
    COLLECTING_INFO = "collecting_info"
    CONFIRMING_APPOINTMENT = "confirming_appointment"
    RESCHEDULING = "rescheduling"
    CANCELING = "canceling"

class Intent(str, Enum):
    SCHEDULE = "schedule"
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"
    OTHER = "other"

class ServiceType(str, Enum):
    CHIROPRACTIC = "chiropractic"
    ACUPUNCTURE = "acupuncture"
    CUPPING = "cupping"
    CONSULTATION = "consultation"

class Location(str, Enum):
    HIGHLAND_PARK = "highland_park"
    ARLINGTON_HEIGHTS = "arlington_heights"

class Doctor(BaseModel):
    id: str
    name: str
    specialties: List[ServiceType]
    locations: List[Location]
    available_days: List[str] = Field(default_factory=lambda: ["monday", "tuesday", "wednesday", "thursday", "friday"])
    start_time: time = time(9, 0)  # 9:00 AM
    end_time: time = time(17, 0)   # 5:00 PM

class Appointment(BaseModel):
    id: str
    patient_name: str
    patient_phone: str
    service_type: ServiceType
    location: Location
    doctor_id: str
    datetime: datetime
    duration_minutes: int = 60
    status: str = "confirmed"  # confirmed, cancelled, completed
    notes: Optional[str] = None

class AvailableSlot(BaseModel):
    datetime: datetime
    doctor_id: str
    doctor_name: str
    location: Location
    service_type: ServiceType
    duration_minutes: int

class CallState(BaseModel):
    call_sid: str
    current_step: CallStep = CallStep.GREETING
    intent: Optional[Intent] = None
    entities: Dict[str, Any] = Field(default_factory=dict)
    patient_name: Optional[str] = None
    patient_phone: Optional[str] = None
    service_type: Optional[ServiceType] = None
    location: Optional[Location] = None
    doctor_id: Optional[str] = None
    preferred_date: Optional[str] = None
    preferred_time: Optional[str] = None
    appointment_id: Optional[str] = None  # For rescheduling
    available_slots: Optional[List[AvailableSlot]] = None
    created_at: datetime = Field(default_factory=datetime.now)

class IntentResponse(BaseModel):
    intent: Intent
    confidence: float
    entities: Dict[str, Any] = Field(default_factory=dict)
    response_message: str
