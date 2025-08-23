import os
import json
import logging
from openai import OpenAI
from datetime import datetime
from typing import Dict, Any
from .models import IntentResponse, ServiceType, Location, Intent, LLMExtraction

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
            self.client = OpenAI(api_key=api_key)
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            # Continue without OpenAI - will use fallback keyword matching
    
    def parse_intent(self, text: str) -> IntentResponse:
        """Parse user intent and extract entities from text via LLM with strict schema."""
        if not self.client:
            self._init_openai()
        if not self.client:
            raise RuntimeError("OpenAI client not available - check OPENAI_API_KEY environment variable")
        
        try:
            today_iso = datetime.now().date().isoformat()
            intent_values = [intent.value for intent in Intent]
            service_type_values = [service.value for service in ServiceType]
            location_values = [location.value for location in Location]
            
            system_prompt = (
                f"Today is {today_iso} (user local calendar). "
                "Resolve relative dates (e.g., 'this Friday', 'next Tuesday') to the nearest FUTURE calendar date. "
                "If the date would be in the past, return null for preferred_date. "
                "You extract structured slots for a clinic voice agent. "
                "IMPORTANT: Extract ALL available information from the user's utterance. "
                "A single sentence can contain multiple slots (e.g., 'My name is John and I want acupuncture next Tuesday' should extract patient_name, service_type, and preferred_date). "
                "Return STRICT JSON only (no prose), matching this schema: {\n"
                f"  \"intent\": one of {intent_values},\n"
                f"  \"service_type\": one of {service_type_values} or null,\n"
                f"  \"location\": one of {location_values} or null,\n"
                "  \"preferred_date\": ISO date 'YYYY-MM-DD' or null (if ambiguous or in the past, null),\n"
                "  \"patient_name\": string or null,\n"
                "  \"corrections\": array of slot names to overwrite prior values.\n"
                "}\n"
                "Do not include any additional keys or commentary."
            )
            
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
                raise RuntimeError("OpenAI returned empty content")
            try:
                data = json.loads(content)
                extraction = LLMExtraction(**data)
                
                intent = extraction.intent
                entities = {
                    'service_type': extraction.service_type,
                    'location': extraction.location,
                    'preferred_date': extraction.preferred_date,
                    'patient_name': extraction.patient_name,
                    'corrections': extraction.corrections,
                    'speech_text': text,
                }
                
                # Log what we extracted for debugging
                logger.info(f"LLM extracted: intent={intent}, entities={entities}")
                
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
                raise RuntimeError(f"Failed to parse OpenAI response as JSON: {content}")
            except Exception as e:
                logger.error(f"LLMExtraction validation error: {e}")
                raise RuntimeError(f"LLMExtraction validation error: {e}")
                
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise RuntimeError(f"OpenAI API error: {e}")
    

    
    def _generate_response_message(self, intent: str, entities: Dict[str, Any]) -> str:
        """Generate a response message based on intent and entities"""
        if intent == 'schedule':
            if entities.get('service_type') and entities.get('location'):
                return f"I can help you schedule a {entities['service_type']} appointment at our {entities['location']} location. Let me check our available times."
            elif entities.get('service_type'):
                return f"I can help you schedule a {entities['service_type']} appointment. Which location would you prefer - {Location.ARLINGTON_HEIGHTS.value} or {Location.HIGHLAND_PARK.value}?"
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
