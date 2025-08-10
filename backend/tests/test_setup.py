#!/usr/bin/env python3
"""
Test script to verify the clinic voice agent setup
"""

import json
import os
import sys
from pathlib import Path

def test_imports():
    """Test that all required modules can be imported"""
    print("Testing imports...")
    
    try:
        import fastapi
        print("✓ FastAPI imported successfully")
    except ImportError as e:
        print(f"✗ FastAPI import failed: {e}")
        return False
    
    try:
        import uvicorn
        print("✓ Uvicorn imported successfully")
    except ImportError as e:
        print(f"✗ Uvicorn import failed: {e}")
        return False
    
    try:
        import pydantic
        print("✓ Pydantic imported successfully")
    except ImportError as e:
        print(f"✗ Pydantic import failed: {e}")
        return False
    
    try:
        import twilio
        print("✓ Twilio imported successfully")
    except ImportError as e:
        print(f"✗ Twilio import failed: {e}")
        return False
    
    try:
        import openai
        print("✓ OpenAI imported successfully")
    except ImportError as e:
        print(f"✗ OpenAI import failed: {e}")
        return False
    
    return True

def test_project_modules():
    """Test that our project modules can be imported"""
    print("\nTesting project modules...")
    
    try:
        from backend.src.models import ServiceType, Location, Doctor, Appointment
        print("✓ Models imported successfully")
    except ImportError as e:
        print(f"✗ Models import failed: {e}")
        return False
    
    try:
        from backend.src.calendar_service import CalendarService
        print("✓ Calendar service imported successfully")
    except ImportError as e:
        print(f"✗ Calendar service import failed: {e}")
        return False
    
    try:
        from backend.src.nlu import NLUProcessor
        print("✓ NLU processor imported successfully")
    except ImportError as e:
        print(f"✗ NLU processor import failed: {e}")
        return False
    
    try:
        from backend.src.call_flow import CallFlowManager
        print("✓ Call flow manager imported successfully")
    except ImportError as e:
        print(f"✗ Call flow manager import failed: {e}")
        return False
    
    return True

def test_clinic_data():
    """Test that clinic data can be loaded"""
    print("\nTesting clinic data...")
    
    try:
        # Try multiple possible paths for clinic.json
        possible_paths = [
            'data/clinic.json',
            'backend/src/data/clinic.json',
            'src/data/clinic.json'
        ]
        
        clinic_data = None
        for path in possible_paths:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    clinic_data = json.load(f)
                break
        
        if not clinic_data:
            print("✗ clinic.json not found in any expected location")
            return False
        
        # Check required fields
        required_fields = ['locations', 'doctors', 'services', 'business_hours']
        for field in required_fields:
            if field not in clinic_data:
                print(f"✗ Missing required field: {field}")
                return False
        
        print(f"✓ Clinic data loaded successfully")
        print(f"  - {len(clinic_data['locations'])} locations")
        print(f"  - {len(clinic_data['doctors'])} doctors")
        print(f"  - {len(clinic_data['services'])} services")
        
        return True
        
    except FileNotFoundError:
        print("✗ clinic.json not found")
        return False
    except json.JSONDecodeError as e:
        print(f"✗ Invalid JSON in clinic.json: {e}")
        return False

def test_calendar_service():
    """Test calendar service functionality"""
    print("\nTesting calendar service...")
    
    try:
        from backend.src.calendar_service import CalendarService
        from backend.src.models import ServiceType, Location
        
        service = CalendarService()
        
        # Test loading doctors
        doctors = service.doctors
        print(f"✓ Loaded {len(doctors)} doctors")
        
        # Test available slots generation
        slots = service.list_available_slots(
            service_type=ServiceType.CHIROPRACTIC,
            location=Location.DOWNTOWN
        )
        print(f"✓ Generated {len(slots)} available slots")
        
        return True
        
    except Exception as e:
        print(f"✗ Calendar service test failed: {e}")
        return False

def test_nlu_processor():
    """Test NLU processor functionality"""
    print("\nTesting NLU processor...")
    
    try:
        from backend.src.nlu import NLUProcessor
        
        processor = NLUProcessor()
        
        # Test intent parsing
        test_text = "I'd like to schedule a chiropractic appointment at the downtown location"
        result = processor.parse_intent(test_text)
        
        print(f"✓ Intent parsing successful")
        print(f"  - Intent: {result.intent}")
        print(f"  - Confidence: {result.confidence}")
        print(f"  - Entities: {result.entities}")
        
        return True
        
    except Exception as e:
        print(f"✗ NLU processor test failed: {e}")
        return False

def test_call_flow():
    """Test call flow manager"""
    print("\nTesting call flow manager...")
    
    try:
        from backend.src.call_flow import CallFlowManager
        
        manager = CallFlowManager()
        
        # Test call state creation
        call_sid = "test_call_123"
        state = manager.get_or_create_call_state(call_sid)
        
        print(f"✓ Call flow manager initialized")
        print(f"  - Call state created: {state.call_sid}")
        
        return True
        
    except Exception as e:
        print(f"✗ Call flow manager test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("Clinic Voice Agent - Setup Test")
    print("=" * 40)
    
    tests = [
        test_imports,
        test_project_modules,
        test_clinic_data,
        test_calendar_service,
        test_nlu_processor,
        test_call_flow
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("=" * 40)
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Your setup is ready.")
        print("\nNext steps:")
        print("1. Set up your .env file with API keys")
        print("2. Run: uvicorn main:app --reload")
        print("3. Test with: curl http://localhost:8000/health")
    else:
        print("❌ Some tests failed. Please check the errors above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
