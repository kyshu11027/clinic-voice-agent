import logging
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from .models import CallState, ServiceType, Location, Appointment, IntentResponse, CallStep, Intent
from .calendar_service import CalendarService
from .nlu import NLUProcessor

logger = logging.getLogger(__name__)

class CallFlowManager:
    def __init__(self):
        self.call_states: Dict[str, CallState] = {}
        self.calendar_service = CalendarService()
        self.nlu_processor = NLUProcessor()
        
    def _log_state(self, call_state: CallState, label: str) -> None:
        """Log and print a concise snapshot of the current call state for debugging."""
        slots_count = len(call_state.available_slots) if call_state.available_slots else 0
        msg = (
            f"[{label}] call_sid={call_state.call_sid} "
            f"step={call_state.current_step} intent={call_state.intent} "
            f"service_type={call_state.service_type} location={call_state.location} "
            f"patient_name={call_state.patient_name} slots={slots_count}"
        )
        logger.info(msg)
        print(msg, flush=True)

    def _parse_preferred_date(self, speech_text: str) -> Optional[str]:
        """Parse a natural language day into ISO date (YYYY-MM-DD).
        Supports: today, tomorrow, weekdays (monday, next tuesday),
        and specific dates like 'august 18th', 'Aug 18', '8/18', '08-18'.
        If year omitted, chooses the next occurrence (use next year if past).
        """
        import re
        speech = (speech_text or "").lower().strip().replace(",", "")
        today = datetime.now().date()

        # today / tomorrow
        if "today" in speech:
            return today.isoformat()
        if "tomorrow" in speech:
            return (today + timedelta(days=1)).isoformat()

        # Weekdays (monday, next tuesday)
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for idx, name in enumerate(weekdays):
            if name in speech:
                target_weekday = idx  # Monday=0
                days_ahead = (target_weekday - today.weekday()) % 7
                # If 'next' mentioned or the same day name and it's too late, bump a week
                if "next" in speech or days_ahead == 0:
                    days_ahead = (days_ahead or 7)
                return (today + timedelta(days=days_ahead)).isoformat()

        # Month name + day (august 18th, aug 18)
        month_map = {
            "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
            "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
            "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
            "nov": 11, "november": 11, "dec": 12, "december": 12
        }
        m = re.search(r"\b([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\b", speech)
        if m:
            month_token = m.group(1)
            day = int(m.group(2))
            if month_token in month_map and 1 <= day <= 31:
                month = month_map[month_token]
                year = today.year
                try:
                    candidate = datetime(year, month, day).date()
                except ValueError:
                    candidate = None
                if candidate:
                    if candidate < today:
                        # assume user means the next occurrence (next year)
                        try:
                            candidate = datetime(year + 1, month, day).date()
                        except ValueError:
                            candidate = None
                    if candidate:
                        return candidate.isoformat()

        # Numeric formats mm/dd or mm-dd
        m2 = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", speech)
        if m2:
            mm = int(m2.group(1))
            dd = int(m2.group(2))
            yy = m2.group(3)
            year = today.year
            if yy:
                y = int(yy)
                if y < 100:
                    y += 2000
                year = y
            try:
                candidate = datetime(year, mm, dd).date()
                if not yy and candidate < today:
                    candidate = datetime(year + 1, mm, dd).date()
                return candidate.isoformat()
            except ValueError:
                pass

        return None
        
    def get_or_create_call_state(self, call_sid: str) -> CallState:
        """Get existing call state or create new one"""
        if call_sid not in self.call_states:
            self.call_states[call_sid] = CallState(call_sid=call_sid)
            logger.info(f"Created new call state for {call_sid}")
        self._log_state(self.call_states[call_sid], "get_or_create")
        return self.call_states[call_sid]
    
    def process_speech_input(self, call_sid: str, speech_text: str) -> str:
        """Process speech input and return appropriate response"""
        call_state = self.get_or_create_call_state(call_sid)
        self._log_state(call_state, "process_speech_input:entry")
        
        # Parse intent and entities
        intent_response = self.nlu_processor.parse_intent(speech_text)
        
        # Update call state
        call_state.intent = intent_response.intent
        call_state.entities.update(intent_response.entities)
        self._log_state(call_state, "process_speech_input:after_parse")
        
        # Route based on current step and intent
        if call_state.current_step == CallStep.GREETING:
            return self._handle_greeting_step(call_state, intent_response)
        elif call_state.current_step == CallStep.COLLECTING_INFO:
            return self._handle_collecting_info_step(call_state, intent_response)
        elif call_state.current_step == CallStep.CONFIRMING_APPOINTMENT:
            return self._handle_confirming_appointment_step(call_state, intent_response)
        elif call_state.current_step == CallStep.RESCHEDULING:
            return self._handle_rescheduling_step(call_state, intent_response)
        elif call_state.current_step == CallStep.CANCELING:
            return self._handle_canceling_step(call_state, intent_response)
        else:
            return "I'm sorry, I didn't understand. How can I help you today?"
    
    def _handle_greeting_step(self, call_state: CallState, intent_response: IntentResponse) -> str:
        """Handle the initial greeting step"""
        self._log_state(call_state, "greeting:entry")
        if intent_response.intent == Intent.SCHEDULE:
            call_state.current_step = CallStep.COLLECTING_INFO
            self._log_state(call_state, "greeting:to_collecting_info")
            return "I'd be happy to help you schedule an appointment. Let me gather some information from you. What type of service would you like - chiropractic, acupuncture, cupping, or consultation?"
        elif intent_response.intent == Intent.RESCHEDULE:
            call_state.current_step = CallStep.RESCHEDULING
            self._log_state(call_state, "greeting:to_rescheduling")
            return "I can help you reschedule your appointment. First, what's your name?"
        elif intent_response.intent == Intent.CANCEL:
            call_state.current_step = CallStep.CANCELING
            self._log_state(call_state, "greeting:to_canceling")
            return "I can help you cancel your appointment. First, what's your name?"
        else:
            return "I can help you with scheduling, rescheduling, or canceling appointments. What would you like to do?"
    
    def _start_scheduling_flow(self, call_state: CallState, entities: Dict) -> str:
        """Start the scheduling flow"""
        # Update call state with extracted entities
        if entities.get('service_type'):
            try:
                call_state.service_type = ServiceType(entities['service_type'])
            except ValueError:
                pass
        
        if entities.get('location'):
            try:
                call_state.location = Location(entities['location'])
            except ValueError:
                pass
        
        if entities.get('patient_name'):
            call_state.patient_name = entities['patient_name']
        
        # Check what information we still need
        missing_info = []
        
        if not call_state.service_type:
            missing_info.append("service type")
        if not call_state.location:
            missing_info.append("location")
        if not call_state.patient_name:
            missing_info.append("your name")
        
        if missing_info:
            missing_str = ", ".join(missing_info)
            return f"I need a few more details to schedule your appointment. Please tell me: {missing_str}."
        else:
            # We have enough info to look for slots
            return self._find_available_slots(call_state)
    
    def _handle_collecting_info_step(self, call_state: CallState, intent_response: IntentResponse) -> str:
        """Handle the information collection step"""
        self._log_state(call_state, "collecting_info:entry")
        # Update call state with new information
        entities = intent_response.entities
        speech_text = intent_response.entities.get('speech_text', '').lower()
        
        # Step 1: Get service type
        if not call_state.service_type:
            if entities.get('service_type'):
                try:
                    call_state.service_type = ServiceType(entities['service_type'])
                except ValueError:
                    pass
            
            if not call_state.service_type:
                # Check for service type in speech
                if any(word in speech_text for word in ['chiropractic', 'adjustment']):
                    call_state.service_type = ServiceType.CHIROPRACTIC
                elif 'acupuncture' in speech_text:
                    call_state.service_type = ServiceType.ACUPUNCTURE
                elif 'cupping' in speech_text:
                    call_state.service_type = ServiceType.CUPPING
                elif any(word in speech_text for word in ['consultation', 'consult']):
                    call_state.service_type = ServiceType.CONSULTATION
                else:
                    self._log_state(call_state, "collecting_info:ask_service_type")
                    return "I didn't catch the service type. Please choose from: chiropractic, acupuncture, cupping, or consultation."
            
            # Move to next step
            self._log_state(call_state, "collecting_info:got_service_type")
            return "Great! Which location would you prefer - Highland Park or Arlington Heights?"
        
        # Step 2: Get location
        elif not call_state.location:
            if entities.get('location'):
                try:
                    call_state.location = Location(entities['location'])
                except ValueError:
                    pass
            
            if not call_state.location:
                # Check for location in speech
                if any(word in speech_text for word in ['highland park']):
                    call_state.location = Location.HIGHLAND_PARK
                elif any(word in speech_text for word in ['arlington heights']):
                    call_state.location = Location.ARLINGTON_HEIGHTS
                else:
                    self._log_state(call_state, "collecting_info:ask_location")
                    return "I didn't catch the location. Please choose: Highland Park or Arlington Heights."
            
            # Move to next step
            self._log_state(call_state, "collecting_info:got_location")
            return "What day would you like to come in? You can say today, tomorrow, or a weekday like Monday or next Tuesday."
        
        # Step 3: Get preferred date
        elif not call_state.preferred_date:
            # Try to infer from entities or speech
            if entities.get('preferred_date'):
                call_state.preferred_date = entities['preferred_date']
            else:
                inferred = self._parse_preferred_date(speech_text)
                if inferred:
                    call_state.preferred_date = inferred
                else:
                    self._log_state(call_state, "collecting_info:ask_date")
                    return "What day would you like to come in? You can say today, tomorrow, or a weekday like Monday or next Tuesday."

            # Move to next step
            self._log_state(call_state, "collecting_info:got_date")
            return "Thanks! Lastly, what's your name?"

        # Step 4: Get patient name
        elif not call_state.patient_name:
            if entities.get('patient_name'):
                call_state.patient_name = entities['patient_name']
            else:
                # Try to extract name from speech (simple approach)
                import re
                # Look for common name patterns
                name_match = re.search(r'my name is (\w+)', speech_text)
                if name_match:
                    call_state.patient_name = name_match.group(1).title()
                else:
                    # Just use the first few words as name
                    words = speech_text.split()
                    if len(words) >= 2:
                        call_state.patient_name = f"{words[0].title()} {words[1].title()}"
                    else:
                        self._log_state(call_state, "collecting_info:ask_name")
                        return "I didn't catch your name. Please tell me your name."
            
            # We have all the information, find available slots
            self._log_state(call_state, "collecting_info:got_name")
            return self._find_available_slots(call_state)
        
        # Fallback - should not reach here
        return "I'm sorry, I'm having trouble understanding. Please start over."
    
    def _find_available_slots(self, call_state: CallState) -> str:
        """Find available appointment slots"""
        self._log_state(call_state, "find_slots:entry")
        # Ensure required fields are present
        if not call_state.service_type or not call_state.location:
            return "I'm sorry, I need both service type and location to find available slots."
        if not call_state.preferred_date:
            self._log_state(call_state, "find_slots:missing_date")
            return "Which day would you like to come in?"
            
        try:
            # Normalize preferred_date to ISO if a natural language label slipped through
            date_str = call_state.preferred_date or ""
            try:
                parsed_day = datetime.fromisoformat(date_str)
            except ValueError:
                inferred = self._parse_preferred_date(date_str)
                if not inferred:
                    self._log_state(call_state, "find_slots:invalid_date")
                    return "I couldn't understand the date. Please say today, tomorrow, or a weekday like next Tuesday."
                call_state.preferred_date = inferred
                parsed_day = datetime.fromisoformat(inferred)

            # Limit search to the selected day only
            day_start = parsed_day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1) - timedelta(seconds=1)
            slots = self.calendar_service.list_available_slots(
                service_type=call_state.service_type,
                location=call_state.location,
                date_range=(day_start, day_end)
            )
            
            if not slots:
                return f"I'm sorry, but I don't see any available {call_state.service_type.value} appointments at our {call_state.location.value} location in the next week. Please call back later or try a different location."
            
            # For MVP, we'll offer the first 3 available slots
            available_slots = slots[:3]
            call_state.available_slots = available_slots
            
            # Format the response
            slot_descriptions = []
            for i, slot in enumerate(available_slots, 1):
                date_str = slot.datetime.strftime("%A, %B %d")
                time_str = slot.datetime.strftime("%I:%M %p")
                slot_descriptions.append(f"{i}. {date_str} at {time_str} with {slot.doctor_name}")
            
            slots_text = ". ".join(slot_descriptions)
            
            call_state.current_step = CallStep.CONFIRMING_APPOINTMENT
            self._log_state(call_state, "find_slots:to_confirming")
            return f"Great! I found some available {call_state.service_type.value} appointments at our {call_state.location.value} location. Here are your options: {slots_text}. Which one would you like? Please say the number."
            
        except Exception as e:
            logger.error(f"Error finding available slots: {e}")
            return "I'm sorry, I'm having trouble checking our availability right now. Please call back in a few minutes."
    
    def _handle_confirming_appointment_step(self, call_state: CallState, intent_response: IntentResponse) -> str:
        """Handle appointment confirmation step"""
        self._log_state(call_state, "confirming:entry")
        speech_text = intent_response.entities.get('speech_text', '').lower()
        
        # Try to extract slot number
        import re
        number_match = re.search(r'(\d+)', speech_text)
        
        if number_match:
            slot_number = int(number_match.group(1))
            if call_state.available_slots and 1 <= slot_number <= len(call_state.available_slots):
                selected_slot = call_state.available_slots[slot_number - 1]
                
                # Ensure all required fields are present
                if not call_state.service_type or not call_state.location or not call_state.patient_name:
                    return "I'm sorry, I'm missing some information. Please start over."
                
                # Create the appointment
                appointment = self.calendar_service.create_appointment(
                    service_type=call_state.service_type,
                    location=call_state.location,
                    doctor_id=selected_slot.doctor_id,
                    datetime_obj=selected_slot.datetime,
                    patient_name=call_state.patient_name,
                    patient_phone="unknown"  # We don't have phone number in MVP
                )
                
                if appointment:
                    date_str = selected_slot.datetime.strftime("%A, %B %d")
                    time_str = selected_slot.datetime.strftime("%I:%M %p")
                    
                    # Clear call state
                    del self.call_states[call_state.call_sid]
                    print(f"[confirming:booked] call_sid={call_state.call_sid} appointment_id={appointment.id}", flush=True)
                    
                    return f"Perfect! I've scheduled your {call_state.service_type.value} appointment with {selected_slot.doctor_name} on {date_str} at {time_str} at our {call_state.location.value} location. You'll receive a confirmation shortly. Thank you for calling!"
                else:
                    return "I'm sorry, I wasn't able to schedule your appointment. Please call back and try again."
            else:
                if call_state.available_slots:
                    return f"Please choose a number between 1 and {len(call_state.available_slots)}."
                else:
                    return "Please choose a valid appointment number."
        else:
            return "I didn't catch which appointment time you'd like. Please say the number of your preferred time."
    
    def _handle_rescheduling_step(self, call_state: CallState, intent_response: IntentResponse) -> str:
        """Handle rescheduling step"""
        self._log_state(call_state, "rescheduling:entry")
        # For MVP, we'll just acknowledge the request
        return "I understand you'd like to reschedule your appointment. This feature is coming soon! Please call our office directly to reschedule."
    
    def _handle_canceling_step(self, call_state: CallState, intent_response: IntentResponse) -> str:
        """Handle appointment cancellation step"""
        self._log_state(call_state, "canceling:entry")
        # For MVP, we'll just acknowledge the request
        return "I understand you'd like to cancel your appointment. This feature is coming soon! Please call our office directly to cancel."
    
    def cleanup_old_states(self, max_age_hours: int = 24):
        """Clean up old call states"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        old_call_sids = [
            call_sid for call_sid, state in self.call_states.items()
            if state.created_at < cutoff_time
        ]
        
        for call_sid in old_call_sids:
            del self.call_states[call_sid]
            logger.info(f"Cleaned up old call state: {call_sid}")
