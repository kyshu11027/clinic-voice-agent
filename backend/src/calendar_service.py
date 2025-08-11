import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from google.oauth2 import service_account
from googleapiclient.discovery import build

from .models import Appointment, AvailableSlot, Doctor, ServiceType, Location

logger = logging.getLogger(__name__)

class CalendarService:
    def __init__(self):
        self.service = None
        self.clinic_data = self._load_clinic_data()
        self.doctors = self._load_doctors()
        
    def _load_clinic_data(self) -> Dict[str, Any]:
        """Load clinic configuration data"""
        try:
            # Try multiple possible paths for clinic.json
            possible_paths = [
                'data/clinic.json',
                'src/data/clinic.json',
                os.path.join(os.path.dirname(__file__), 'data/clinic.json')
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    with open(path, 'r') as f:
                        return json.load(f)
            
            logger.error("clinic.json not found in any expected location")
            return {}
        except FileNotFoundError:
            logger.error("clinic.json not found")
            return {}
    
    def _load_doctors(self) -> List[Doctor]:
        """Load doctors from clinic data"""
        doctors = []
        for doc_data in self.clinic_data.get('doctors', []):
            doctor = Doctor(
                id=doc_data['id'],
                name=doc_data['name'],
                specialties=[ServiceType(s) for s in doc_data['specialties']],
                locations=[Location(l) for l in doc_data['locations']],
                available_days=doc_data.get('available_days', []),
                start_time=datetime.strptime(doc_data['start_time'], '%H:%M').time(),
                end_time=datetime.strptime(doc_data['end_time'], '%H:%M').time()
            )
            doctors.append(doctor)
        return doctors
    
    def _init_google_calendar(self):
        """Initialize Google Calendar API service"""
        if self.service:
            return
            
        credentials_json = os.getenv('GOOGLE_CALENDAR_CREDENTIALS_JSON')
        if not credentials_json:
            logger.warning("Google Calendar credentials not configured")
            return
            
        try:
            credentials = service_account.Credentials.from_service_account_info(
                json.loads(credentials_json),
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            self.service = build('calendar', 'v3', credentials=credentials)
            logger.info("Google Calendar service initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Google Calendar: {e}")
    
    def list_available_slots(
        self, 
        service_type: ServiceType, 
        location: Location, 
        date_range: Optional[tuple] = None
    ) -> List[AvailableSlot]:
        """List available appointment slots for a service type and location"""
        if date_range is None:
            # Default to next 7 days
            start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=7)
        else:
            start_date, end_date = date_range
        
        available_slots = []
        
        # For MVP, we'll generate mock available slots
        # In production, this would query Google Calendar
        current_date = start_date
        while current_date <= end_date:
            day_name = current_date.strftime('%A').lower()
            
            # Check if clinic is open on this day
            business_hours = self.clinic_data.get('business_hours', {}).get(day_name, {})
            if business_hours.get('open') == 'closed':
                current_date += timedelta(days=1)
                continue
            
            # Find doctors available for this service and location
            available_doctors = [
                doc for doc in self.doctors
                if service_type in doc.specialties 
                and location in doc.locations
                and day_name in doc.available_days
            ]
            
            for doctor in available_doctors:
                # Generate time slots for this doctor
                start_time = max(
                    datetime.strptime(business_hours['open'], '%H:%M').time(),
                    doctor.start_time
                )
                end_time = min(
                    datetime.strptime(business_hours['close'], '%H:%M').time(),
                    doctor.end_time
                )
                
                # Generate 30-minute slots
                current_time = start_time
                while current_time < end_time:
                    slot_datetime = datetime.combine(current_date.date(), current_time)
                    
                    # Skip if slot is in the past
                    if slot_datetime > datetime.now():
                        slot = AvailableSlot(
                            datetime=slot_datetime,
                            doctor_id=doctor.id,
                            doctor_name=doctor.name,
                            location=location,
                            service_type=service_type,
                            duration_minutes=60
                        )
                        available_slots.append(slot)
                    
                    # Move to next slot (30 minutes)
                    current_time = (datetime.combine(datetime.today(), current_time) + 
                                  timedelta(minutes=30)).time()
            
            current_date += timedelta(days=1)
        
        return available_slots
    
    def create_appointment(
        self, 
        service_type: ServiceType, 
        location: Location, 
        doctor_id: str, 
        datetime_obj: datetime,
        patient_name: str,
        patient_phone: str
    ) -> Optional[Appointment]:
        """Create a new appointment"""
        try:
            # For MVP, we'll create a mock appointment
            # In production, this would create an event in Google Calendar
            appointment_id = f"apt_{datetime_obj.strftime('%Y%m%d_%H%M')}_{patient_name.replace(' ', '_')}"
            
            appointment = Appointment(
                id=appointment_id,
                patient_name=patient_name,
                patient_phone=patient_phone,
                service_type=service_type,
                location=location,
                doctor_id=doctor_id,
                datetime=datetime_obj,
                duration_minutes=60,
                status="confirmed"
            )
            
            logger.info(f"Created appointment: {appointment_id}")
            return appointment
            
        except Exception as e:
            logger.error(f"Failed to create appointment: {e}")
            return None
    
    def reschedule_appointment(
        self, 
        appointment_id: str, 
        new_datetime: datetime
    ) -> bool:
        """Reschedule an existing appointment"""
        try:
            # For MVP, we'll just log the reschedule
            # In production, this would update the Google Calendar event
            logger.info(f"Rescheduled appointment {appointment_id} to {new_datetime}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to reschedule appointment: {e}")
            return False
    
    def get_appointment(self, appointment_id: str) -> Optional[Appointment]:
        """Get appointment by ID"""
        # For MVP, return None (appointments not persisted)
        # In production, this would query Google Calendar
        return None
    
    def find_appointments_by_patient(self, patient_name: str, patient_phone: str) -> List[Appointment]:
        """Find appointments for a patient"""
        # For MVP, return empty list
        # In production, this would query Google Calendar
        return []
