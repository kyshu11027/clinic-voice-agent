import os
import json
import logging
import openai
from typing import Dict, Any, Optional
from .models import IntentResponse, ServiceType, Location

logger = logging.getLogger(__name__)

class NLUProcessor:
    def __init__(self):
        self.client = None
        self._init_openai()
        
    def _init_openai(self):
        """Initialize OpenAI client"""
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.warning("OpenAI API key not configured")
            return
            
        try:
            self.client = openai.OpenAI(api_key=api_key)
            logger.info("OpenAI client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
    
    def parse_intent(self, text: str) -> IntentResponse:
        """Parse user intent and extract entities from text"""
        if not self.client:
            # Fallback to basic keyword matching
            return self._fallback_intent_parsing(text)
        
        try:
            system_prompt = """
            You are an AI assistant for a chiropractic and acupuncture clinic. 
            Your job is to understand what the caller wants and extract relevant information.
            
            Extract the following information:
            - intent: "schedule", "reschedule", "cancel", "question", or "other"
            - service_type: "chiropractic", "acupuncture", "massage", "consultation", or null
            - location: "downtown", "west_side", or null
            - doctor_name: name of doctor if mentioned, or null
            - preferred_date: date if mentioned, or null
            - preferred_time: time if mentioned, or null
            - patient_name: caller's name if mentioned, or null
            
            Return a JSON object with these fields.
            """
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.1,
                max_tokens=200
            )
            
            # Parse the response
            content = response.choices[0].message.content
            if not content:
                logger.error("OpenAI returned empty content")
                return self._fallback_intent_parsing(text)
            try:
                result = json.loads(content)
                
                # Validate and clean the result
                intent = result.get('intent', 'other')
                entities = {
                    'service_type': result.get('service_type'),
                    'location': result.get('location'),
                    'doctor_name': result.get('doctor_name'),
                    'preferred_date': result.get('preferred_date'),
                    'preferred_time': result.get('preferred_time'),
                    'patient_name': result.get('patient_name')
                }
                
                # Generate response message
                response_message = self._generate_response_message(intent, entities)
                
                return IntentResponse(
                    intent=intent,
                    confidence=0.9,  # High confidence for GPT-4
                    entities=entities,
                    response_message=response_message
                )
                
            except json.JSONDecodeError:
                logger.error(f"Failed to parse OpenAI response as JSON: {content}")
                return self._fallback_intent_parsing(text)
                
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return self._fallback_intent_parsing(text)
    
    def _fallback_intent_parsing(self, text: str) -> IntentResponse:
        """Fallback intent parsing using keyword matching"""
        text_lower = text.lower()
        entities = {}
        
        # Determine intent
        if any(word in text_lower for word in ['schedule', 'book', 'make appointment', 'new appointment']):
            intent = 'schedule'
        elif any(word in text_lower for word in ['reschedule', 'change appointment', 'move appointment']):
            intent = 'reschedule'
        elif any(word in text_lower for word in ['cancel', 'cancel appointment']):
            intent = 'cancel'
        else:
            intent = 'other'
        
        # Extract service type
        if 'chiropractic' in text_lower or 'adjustment' in text_lower:
            entities['service_type'] = 'chiropractic'
        elif 'acupuncture' in text_lower:
            entities['service_type'] = 'acupuncture'
        elif 'massage' in text_lower:
            entities['service_type'] = 'massage'
        elif 'consultation' in text_lower or 'consult' in text_lower:
            entities['service_type'] = 'consultation'
        
        # Extract location
        if 'downtown' in text_lower:
            entities['location'] = 'downtown'
        elif 'west side' in text_lower or 'westside' in text_lower:
            entities['location'] = 'west_side'
        
        # Extract doctor name (basic pattern matching)
        import re
        doctor_patterns = [
            r'dr\.?\s+(\w+)',
            r'doctor\s+(\w+)',
            r'(\w+)\s+smith',
            r'(\w+)\s+johnson',
            r'(\w+)\s+lee'
        ]
        
        for pattern in doctor_patterns:
            match = re.search(pattern, text_lower)
            if match:
                entities['doctor_name'] = match.group(1).title()
                break
        
        response_message = self._generate_response_message(intent, entities)
        
        return IntentResponse(
            intent=intent,
            confidence=0.6,  # Lower confidence for fallback
            entities=entities,
            response_message=response_message
        )
    
    def _generate_response_message(self, intent: str, entities: Dict[str, Any]) -> str:
        """Generate a response message based on intent and entities"""
        if intent == 'schedule':
            if entities.get('service_type') and entities.get('location'):
                return f"I can help you schedule a {entities['service_type']} appointment at our {entities['location']} location. Let me check our available times."
            elif entities.get('service_type'):
                return f"I can help you schedule a {entities['service_type']} appointment. Which location would you prefer - downtown or west side?"
            elif entities.get('location'):
                return f"I can help you schedule an appointment at our {entities['location']} location. What type of service would you like?"
            else:
                return "I can help you schedule an appointment. What type of service would you like and which location do you prefer?"
        
        elif intent == 'reschedule':
            return "I can help you reschedule your appointment. What's your name and when is your current appointment?"
        
        elif intent == 'cancel':
            return "I can help you cancel your appointment. What's your name and when is your appointment?"
        
        else:
            return "I understand you said something. I can help you with scheduling, rescheduling, or canceling appointments. What would you like to do?"
