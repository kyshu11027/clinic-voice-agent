import logging
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from .models import CallState, ServiceType, Location, Appointment, IntentResponse
from .calendar_service import CalendarService
from .nlu import NLUProcessor

logger = logging.getLogger(__name__)

class CallFlowManager:
    def __init__(self):
        self.call_states: Dict[str, CallState] = {}
        self.calendar_service = CalendarService()
        self.nlu_processor = NLUProcessor()
        
    def get_or_create_call_state(self, call_sid: str) -> CallState:
        """Get existing call state or create new one"""
        if call_sid not in self.call_states:
            self.call_states[call_sid] = CallState(call_sid=call_sid)
            logger.info(f"Created new call state for {call_sid}")
        
        return self.call_states[call_sid]
    
    def process_speech_input(self, call_sid: str, speech_text: str) -> str:
        """Process speech input and return appropriate response"""
        call_state = self.get_or_create_call_state(call_sid)
        
        # Parse intent and entities
        intent_response = self.nlu_processor.parse_intent(speech_text)
        
        # Update call state
        call_state.intent = intent_response.intent
        call_state.entities.update(intent_response.entities)
        
        # Route based on current step and intent
        if call_state.current_step == "greeting":
            return self._handle_greeting_step(call_state, intent_response)
        elif call_state.current_step == "collecting_info":
            return self._handle_collecting_info_step(call_state, intent_response)
        elif call_state.current_step == "confirming_appointment":
            return self._handle_confirming_appointment_step(call_state, intent_response)
        elif call_state.current_step == "rescheduling":
            return self._handle_rescheduling_step(call_state, intent_response)
        else:
            return "I'm sorry, I didn't understand. How can I help you today?"
    
    def _handle_greeting_step(self, call_state: CallState, intent_response: IntentResponse) -> str:
        """Handle the initial greeting step"""
        if intent_response.intent == "schedule":
            call_state.current_step = "collecting_info"
            return self._start_scheduling_flow(call_state, intent_response.entities)
        elif intent_response.intent == "reschedule":
            call_state.current_step = "rescheduling"
            return "I can help you reschedule your appointment. What's your name and when is your current appointment?"
        elif intent_response.intent == "cancel":
            return "I can help you cancel your appointment. What's your name and when is your appointment?"
        else:
            return intent_response.response_message
    
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
        # Update call state with new information
        entities = intent_response.entities
        
        if entities.get('service_type') and not call_state.service_type:
            try:
                call_state.service_type = ServiceType(entities['service_type'])
            except ValueError:
                pass
        
        if entities.get('location') and not call_state.location:
            try:
                call_state.location = Location(entities['location'])
            except ValueError:
                pass
        
        if entities.get('patient_name') and not call_state.patient_name:
            call_state.patient_name = entities['patient_name']
        
        # Check if we have all required information
        if call_state.service_type and call_state.location and call_state.patient_name:
            return self._find_available_slots(call_state)
        else:
            # Still missing information
            missing_info = []
            if not call_state.service_type:
                missing_info.append("service type")
            if not call_state.location:
                missing_info.append("location")
            if not call_state.patient_name:
                missing_info.append("your name")
            
            missing_str = ", ".join(missing_info)
            return f"I still need: {missing_str}. Please provide this information."
    
    def _find_available_slots(self, call_state: CallState) -> str:
        """Find available appointment slots"""
        # Ensure required fields are present
        if not call_state.service_type or not call_state.location:
            return "I'm sorry, I need both service type and location to find available slots."
            
        try:
            slots = self.calendar_service.list_available_slots(
                service_type=call_state.service_type,
                location=call_state.location
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
            
            call_state.current_step = "confirming_appointment"
            return f"Great! I found some available {call_state.service_type.value} appointments at our {call_state.location.value} location. Here are your options: {slots_text}. Which one would you like? Please say the number."
            
        except Exception as e:
            logger.error(f"Error finding available slots: {e}")
            return "I'm sorry, I'm having trouble checking our availability right now. Please call back in a few minutes."
    
    def _handle_confirming_appointment_step(self, call_state: CallState, intent_response: IntentResponse) -> str:
        """Handle appointment confirmation step"""
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
        # For MVP, we'll just acknowledge the request
        return "I understand you'd like to reschedule your appointment. This feature is coming soon! Please call our office directly to reschedule."
    
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
