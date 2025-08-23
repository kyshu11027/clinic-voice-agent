import logging
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from .models import CallState, ServiceType, Location, IntentResponse, CallStep, Intent
from .calendar_service import CalendarService
from .nlu import NLUProcessor

logger = logging.getLogger(__name__)

# Required slots per intent (extensible)
REQUIRED_SLOTS: Dict[Intent, List[str]] = {
    Intent.SCHEDULE: ["service_type", "location", "preferred_date", "patient_name", "patient_phone"],
    Intent.RESCHEDULE: ["patient_name", "preferred_date", "patient_phone"],
    Intent.CANCEL: ["patient_name", "patient_phone"],
    Intent.OTHER: [],
}

PROMPTS: Dict[str, str] = {
    "intent": "Would you like to schedule, reschedule, or cancel an appointment?",
    "service_type": "What type of service would you like: chiropractic, acupuncture, massage, or consultation?",
    "location": "Which location do you prefer: Highland Park or Arlington Heights?",
    "preferred_date": "What day would you like to come in? You can say today, tomorrow, or a weekday like next Tuesday, or a specific date like August 18th.",
    "patient_name": "What's your name?",
    "patient_phone": "Please enter your phone number using your keypad, then press the pound sign.",
}

class CallFlowManager:
    def __init__(self):
        self.call_states: Dict[str, CallState] = {}
        self.calendar_service = CalendarService()
        self.nlu_processor = NLUProcessor()
        
    def _log_state(self, call_state: CallState, label: str) -> None:
        """Log and print a concise snapshot of the current call state for debugging."""
        slots_count = len(call_state.available_slots) if call_state.available_slots else 0
        msg = (
            f"[{label}] call_sid={call_state.call_sid} \n"
            f"step={call_state.current_step} intent={call_state.intent} \n"
            f"service_type={call_state.service_type} location={call_state.location} \n"
            f"patient_name={call_state.patient_name} patient_phone={call_state.patient_phone} slots={slots_count} \n"
            f"preferred_date={call_state.preferred_date} \n"
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
        
        # Parse intent and entities (LLM-based with strict schema and fallback)
        intent_response = self.nlu_processor.parse_intent(speech_text)
        
        # Apply corrections and update slots deterministically
        ents = intent_response.entities
        corrections = set((ents.get('corrections') or []))
        
        # Log what we received for debugging
        logger.info(f"Processing entities: {ents}, corrections: {corrections}")

        # Update intent first
        call_state.intent = intent_response.intent
        # Slot updates: LLM-first approach - allow NLU to populate slots normally, but prioritize corrections
        if 'service_type' in ents and (call_state.service_type is None or 'service_type' in corrections):
            try:
                call_state.service_type = ServiceType(ents['service_type']) if ents['service_type'] else None
            except ValueError:
                pass
        if 'location' in ents and (call_state.location is None or 'location' in corrections):
            try:
                call_state.location = Location(ents['location']) if ents['location'] else None
            except ValueError:
                pass
        if 'preferred_date' in ents and (call_state.preferred_date is None or 'preferred_date' in corrections):
            pd = ents['preferred_date']
            if pd:
                try:
                    d = datetime.fromisoformat(pd).date()
                    if d >= datetime.now().date():
                        call_state.preferred_date = pd
                except Exception:
                    # Try to parse and normalize the date
                    inferred = self._parse_preferred_date(pd)
                    if inferred:
                        try:
                            d2 = datetime.fromisoformat(inferred).date()
                            if d2 >= datetime.now().date():
                                call_state.preferred_date = inferred
                        except Exception:
                            pass
        if 'patient_name' in ents and (call_state.patient_name is None or 'patient_name' in corrections):
            call_state.patient_name = ents['patient_name']
        if 'patient_phone' in ents and (call_state.patient_phone is None or 'patient_phone' in corrections):
            call_state.patient_phone = ents['patient_phone']

        # Keep entities echo for debugging
        call_state.entities.update(intent_response.entities)
        self._log_state(call_state, "process_speech_input:after_parse")
        
        # Route based on current step and intent
        if call_state.current_step == CallStep.GREETING:
            return self._handle_greeting_step(call_state, intent_response)
        elif call_state.current_step in (CallStep.COLLECTING_INFO, CallStep.RESCHEDULING, CallStep.CANCELING):
            # Unify slot filling handling regardless of current step to tolerate out-of-order answers
            return self._handle_collecting_info_step(call_state, intent_response)
        elif call_state.current_step == CallStep.CONFIRMING_APPOINTMENT:
            return self._handle_confirming_appointment_step(call_state, intent_response)
        else:
            # Safeguard: if state is unknown, continue slot filling deterministically
            return self._handle_collecting_info_step(call_state, intent_response)
    
    def _handle_greeting_step(self, call_state: CallState, intent_response: IntentResponse) -> str:
        """Handle the initial greeting step"""
        self._log_state(call_state, "greeting:entry")
        if intent_response.intent == Intent.SCHEDULE:
            # Check if we already have all the required information
            if (call_state.service_type and call_state.location and 
                call_state.preferred_date and call_state.patient_name and call_state.patient_phone):
                self._log_state(call_state, "greeting:all_slots_filled")
                return self._find_available_slots(call_state)
            
            call_state.current_step = CallStep.COLLECTING_INFO
            self._log_state(call_state, "greeting:to_collecting_info")
            
            # Check what information we still need and ask for the next missing piece
            if not call_state.service_type:
                return "I'd be happy to help you schedule an appointment. What type of service would you like - chiropractic, acupuncture, cupping, or consultation?"
            elif not call_state.location:
                return PROMPTS["location"]
            elif not call_state.preferred_date:
                return PROMPTS["preferred_date"]
            elif not call_state.patient_name:
                return PROMPTS["patient_name"]
            elif not call_state.patient_phone:
                return PROMPTS["patient_phone"]
            else:
                # This shouldn't happen since we already checked for all slots in greeting
                return "Let me find available slots for you."
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
                self._log_state(call_state, "collecting_info:ask_service_type")
                return "I didn't catch the service type. Please choose from: chiropractic, acupuncture, cupping, or consultation."
            
            # Move to next step
            self._log_state(call_state, "collecting_info:got_service_type")
            if not call_state.location:
                return PROMPTS["location"]
            return "Great!"
        
        # Step 2: Get location
        elif not call_state.location:
            if entities.get('location'):
                try:
                    call_state.location = Location(entities['location'])
                except ValueError:
                    pass
            if not call_state.location:
                self._log_state(call_state, "collecting_info:ask_location")
                return "Please provide the location you'd like to visit. Please choose: Highland Park or Arlington Heights."
            
            # Move to next step
            self._log_state(call_state, "collecting_info:got_location")
            if not call_state.preferred_date:
                return PROMPTS["preferred_date"]
            return "Thanks!"
        
        # Step 3: Get preferred date
        elif not call_state.preferred_date:
            # Expect the date from NLU
            if entities.get('preferred_date'):
                # Accept only if not in the past
                try:
                    d = datetime.fromisoformat(entities['preferred_date']).date()
                    if d >= datetime.now().date():
                        call_state.preferred_date = entities['preferred_date']
                    else:
                        self._log_state(call_state, "collecting_info:ask_date")
                        return "That date seems to be in the past. Please say today, tomorrow, or a weekday like next Tuesday."
                except Exception:
                    # Fallback to inference
                    inferred = self._parse_preferred_date(entities['preferred_date'])
                    if inferred:
                        try:
                            d2 = datetime.fromisoformat(inferred).date()
                            if d2 >= datetime.now().date():
                                call_state.preferred_date = inferred
                            else:
                                self._log_state(call_state, "collecting_info:ask_date")
                                return "That date seems to be in the past. Please say today, tomorrow, or a weekday like next Tuesday."
                        except Exception:
                            self._log_state(call_state, "collecting_info:ask_date")
                            return "I couldn't understand the date. Please say today, tomorrow, or a weekday like next Tuesday."
            else:
                self._log_state(call_state, "collecting_info:ask_date")
                return "What day would you like to come in? You can say today, tomorrow, or a weekday like Monday or next Tuesday."

            # Move to next step
            self._log_state(call_state, "collecting_info:got_date")

            if not call_state.patient_name:
                return PROMPTS["patient_name"]
            return "Thanks!"

        # Step 4: Get patient name
        elif not call_state.patient_name:
            # If user is correcting other slots here, don't infer name from that utterance
            if (entities.get('location') or entities.get('service_type')) and not entities.get('patient_name'):
                self._log_state(call_state, "collecting_info:ask_name")
                return PROMPTS["patient_name"]

            if any(token in speech_text for token in ["actually", "change", "correction"]):
                self._log_state(call_state, "collecting_info:ask_name")
                return PROMPTS["patient_name"]

            # Guard: if the user says another date here (e.g., "next Tuesday"),
            # treat it as a date correction instead of a name.
            if entities.get('preferred_date'):
                call_state.preferred_date = entities['preferred_date']
                self._log_state(call_state, "collecting_info:got_date")
                return PROMPTS["patient_name"]

            # Expect the name from NLU
            if entities.get('patient_name'):
                call_state.patient_name = entities['patient_name']
            else:
                self._log_state(call_state, "collecting_info:ask_name")
                return PROMPTS["patient_name"]
            
            # We have all the information, find available slots
            self._log_state(call_state, "collecting_info:got_name")
            if not call_state.patient_phone:
                return PROMPTS["patient_phone"]
            return "Thanks!"
        
        # Step 5: Get patient phone number
        elif not call_state.patient_phone:
            if entities.get('patient_phone'):
                call_state.patient_phone = entities['patient_phone']
            else:
                self._log_state(call_state, "collecting_info:ask_phone")
                return PROMPTS["patient_phone"]
            
            # We have all the information, find available slots
            self._log_state(call_state, "collecting_info:got_phone")
            return "Thanks!"
        
        # All information collected, find available slots

        return self._find_available_slots(call_state)
    
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
                # Use the proper location name from clinic data
                location_name = "Arlington Heights" if call_state.location.value == "arlington_heights" else "Highland Park"
                return f"I'm sorry, but I don't see any available {call_state.service_type.value} appointments at our {location_name} location for {call_state.preferred_date}. Please call back later or try a different location."
            
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
            # Use the proper location name from clinic data instead of enum value
            location_name = "Arlington Heights" if call_state.location.value == "arlington_heights" else "Highland Park"
            return f"Great! I found some available {call_state.service_type.value} appointments at our {location_name} location. Here are your options: {slots_text}. Which one would you like? Please say the number."
            
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
                if not call_state.service_type or not call_state.location or not call_state.patient_name or not call_state.patient_phone:
                    return "I'm sorry, I'm missing some information. Please start over."
                
                # Create the appointment
                appointment = self.calendar_service.create_appointment(
                    service_type=call_state.service_type,
                    location=call_state.location,
                    doctor_id=selected_slot.doctor_id,
                    datetime_obj=selected_slot.datetime,
                    patient_name=call_state.patient_name,
                    patient_phone=call_state.patient_phone
                )
                
                if appointment:
                    date_str = selected_slot.datetime.strftime("%A, %B %d")
                    time_str = selected_slot.datetime.strftime("%I:%M %p")
                    
                    # Clear call state
                    del self.call_states[call_state.call_sid]
                    print(f"[confirming:booked] call_sid={call_state.call_sid} appointment_id={appointment.id}", flush=True)
                    
                    # Use the proper location name from clinic data
                    location_name = "Arlington Heights" if call_state.location.value == "arlington_heights" else "Highland Park"
                    return f"Perfect! I've scheduled your {call_state.service_type.value} appointment with {selected_slot.doctor_name} on {date_str} at {time_str} at our {location_name} location. You'll receive a confirmation shortly. Thank you for calling!"
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
