import os
import json
import types
from datetime import datetime, timedelta

import pytest

# Ensure package path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.src.call_flow import CallFlowManager
from backend.src.models import Intent
from backend.src.nlu import NLUProcessor


class DummyNLU(NLUProcessor):
    """Deterministic NLU stub returning predefined extractions for testing."""
    def __init__(self, script):
        # do not call super().__init__ (avoids OpenAI init)
        self.client = None
        # script is a list of (utterance_substring, extraction_dict) pairs applied in order
        self.script = script

    def parse_intent(self, text: str):
        # Minimal stand-in for IntentResponse
        from backend.src.models import IntentResponse
        for match, extraction in self.script:
            if match in text:
                return IntentResponse(
                    intent=extraction.get('intent', Intent.SCHEDULE),
                    confidence=0.99,
                    entities={
                        'service_type': extraction.get('service_type'),
                        'location': extraction.get('location'),
                        'preferred_date': extraction.get('preferred_date'),
                        'patient_name': extraction.get('patient_name'),
                        'patient_phone': extraction.get('patient_phone'),
                        'corrections': extraction.get('corrections', []),
                        'speech_text': text,
                    },
                    response_message=""
                )
        # default empty
        return IntentResponse(intent=Intent.SCHEDULE, confidence=0.5, entities={'speech_text': text}, response_message="")


def make_manager_with_stub(script):
    mgr = CallFlowManager()
    mgr.nlu_processor = DummyNLU(script)
    return mgr


def test_schedule_natural_sentence_then_complete():
    today = datetime.now().date()
    next_mon = (today + timedelta((0 - today.weekday()) % 7 or 7))  # next Monday
    # User provides intent + date + location in one utterance
    first_utterance = "I would like to schedule an appointment for next Monday at the Highland Park location"
    script = [
        (first_utterance, {"intent": Intent.SCHEDULE, "location": "highland_park", "preferred_date": next_mon.isoformat()}),
        ("chiropractic", {"service_type": "chiropractic"}),
        ("Kevin Shu", {"patient_name": "Kevin Shu"}),
        ("5551234567", {"patient_phone": "5551234567"}),
    ]

    mgr = make_manager_with_stub(script)
    sid = "test_call_1"

    # Turn 1: natural sentence (intent + date + location)
    msg = mgr.process_speech_input(sid, first_utterance)
    # Should ask for remaining missing slot (service type)
    assert "service" in msg.lower() or "what type" in msg.lower()

    # Turn 2: provide service
    msg = mgr.process_speech_input(sid, "chiropractic")
    # Should ask for name next
    assert "name" in msg.lower()

    # Turn 3: provide name triggers phone number request
    msg = mgr.process_speech_input(sid, "My name is Kevin Shu")
    state_after = mgr.call_states[sid]
    assert state_after.patient_name == "Kevin Shu"
    # Should now ask for phone number
    assert "phone number" in msg.lower()
    
    # Turn 4: provide phone number triggers slot search
    msg = mgr.process_speech_input(sid, "5551234567")
    state_after = mgr.call_states[sid]
    assert state_after.patient_phone == "5551234567"
    # Allow either offering options or reporting no availability
    assert (
        (state_after.available_slots is not None and ("options" in msg.lower() or "here are your" in msg.lower()))
        or ("don't see any available" in msg.lower())
    )


def test_corrections_overwrite_previous_values():
    today = datetime.now().date()
    this_fri = today + timedelta((4 - today.weekday()) % 7)
    next_fri = this_fri + timedelta(days=7)
    script = [
        ("schedule", {"intent": Intent.SCHEDULE}),
        ("Highland Park", {"location": "highland_park"}),
        ("acupuncture", {"service_type": "acupuncture"}),
        ("this Friday", {"preferred_date": this_fri.isoformat()}),
        ("actually Arlington Heights", {"location": "arlington_heights", "corrections": ["location"]}),
        ("actually next Friday", {"preferred_date": next_fri.isoformat(), "corrections": ["preferred_date"]}),
        ("John Doe", {"patient_name": "John Doe"}),
        ("5559876543", {"patient_phone": "5559876543"}),
    ]

    mgr = make_manager_with_stub(script)
    sid = "test_call_2"

    mgr.process_speech_input(sid, "schedule")
    mgr.process_speech_input(sid, "Highland Park")
    mgr.process_speech_input(sid, "acupuncture")
    mgr.process_speech_input(sid, "this Friday")
    # correction of location
    mgr.process_speech_input(sid, "actually Arlington Heights")
    # correction of date
    mgr.process_speech_input(sid, "actually next Friday")
    # final slot
    msg = mgr.process_speech_input(sid, "My name is John Doe")
    state = mgr.call_states[sid]
    assert state.patient_name == "John Doe"
    # Should now ask for phone number
    assert "phone number" in msg.lower()
    
    # Provide phone number
    msg = mgr.process_speech_input(sid, "5559876543")
    state = mgr.call_states[sid]
    assert state.location is not None and state.location.value == "arlington_heights"
    assert state.preferred_date == next_fri.isoformat()
    assert state.service_type is not None and state.service_type.value == "acupuncture"
    assert state.patient_name == "John Doe"
    assert state.patient_phone == "5559876543"
    assert state.available_slots is not None


def test_past_date_reprompt():
    # Provide a past date; bot should reprompt or normalize
    past = (datetime.now() - timedelta(days=30)).date().isoformat()
    script = [
        ("schedule", {"intent": Intent.SCHEDULE}),
        ("Highland Park", {"location": "highland_park"}),
        ("chiropractic", {"service_type": "chiropractic"}),
        ("last month", {"preferred_date": past}),
        ("5551112222", {"patient_phone": "5551112222"}),
    ]
    mgr = make_manager_with_stub(script)
    sid = "test_call_3"
    mgr.process_speech_input(sid, "schedule")
    mgr.process_speech_input(sid, "Highland Park")
    mgr.process_speech_input(sid, "chiropractic")
    msg = mgr.process_speech_input(sid, "last month")
    # Should ask again for a valid day
    assert "day" in msg.lower() or "date" in msg.lower()
    
    # Provide phone number to complete the flow
    mgr.process_speech_input(sid, "5551112222")


def test_next_tuesday_not_captured_as_name():
    today = datetime.now().date()
    # compute next Tuesday explicitly per the date parser logic (Mon=0)
    target_weekday = 1  # Tuesday
    days_ahead = (target_weekday - today.weekday()) % 7 or 7
    next_tuesday = (today + timedelta(days=days_ahead)).isoformat()

    script = [
        ("schedule", {"intent": Intent.SCHEDULE}),
        ("Arlington Heights", {"location": "arlington_heights"}),
        ("acupuncture", {"service_type": "acupuncture"}),
        ("Next Tuesday", {"preferred_date": next_tuesday}),
        ("5553334444", {"patient_phone": "5553334444"}),
    ]

    mgr = make_manager_with_stub(script)
    sid = "test_call_4"

    mgr.process_speech_input(sid, "schedule")
    mgr.process_speech_input(sid, "Arlington Heights")
    mgr.process_speech_input(sid, "acupuncture")
    # When asked for date, user says "Next Tuesday"; should set preferred_date, not name
    msg = mgr.process_speech_input(sid, "Next Tuesday")

    state = mgr.call_states[sid]
    assert state.preferred_date == next_tuesday
    assert state.patient_name is None
    # Bot should now ask for name
    assert "name" in msg.lower()
    
    # Provide phone number to complete the flow
    mgr.process_speech_input(sid, "5553334444")


def test_all_slots_filled_in_single_utterance():
    """Test that when all slots are filled in one utterance, the system goes directly to finding slots"""
    today = datetime.now().date()
    # compute next Tuesday explicitly per the date parser logic (Mon=0)
    target_weekday = 1  # Tuesday
    days_ahead = (target_weekday - today.weekday()) % 7 or 7
    next_tuesday = (today + timedelta(days=days_ahead)).isoformat()

    script = [
        ("Hi. My name is Kevin Shu and I'm trying to schedule an appointment in Arlington Heights. Next Tuesday for acupuncture.", 
         {"intent": Intent.SCHEDULE, 
          "service_type": "acupuncture", 
          "location": "arlington_heights", 
          "preferred_date": next_tuesday, 
          "patient_name": "Kevin Shu",
          "patient_phone": "5555555555"}),
    ]

    mgr = make_manager_with_stub(script)
    sid = "test_call_5"

    # Single utterance with all information should go directly to finding slots
    msg = mgr.process_speech_input(sid, "Hi. My name is Kevin Shu and I'm trying to schedule an appointment in Arlington Heights. Next Tuesday for acupuncture.")

    state = mgr.call_states[sid]
    assert state.service_type is not None and state.service_type.value == "acupuncture"
    assert state.location is not None and state.location.value == "arlington_heights"
    assert state.preferred_date == next_tuesday
    assert state.patient_name == "Kevin Shu"
    assert state.patient_phone == "5555555555"
    
    # Should either offer slots or report no availability (not ask for more info)
    assert not any(prompt in msg.lower() for prompt in ["what type", "which location", "what day", "what's your name", "phone number"])

