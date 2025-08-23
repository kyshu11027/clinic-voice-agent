#!/usr/bin/env python3
"""
Test runner for the Clinic Voice Agent
"""

import sys
import os

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from backend.tests.test_setup import main
from backend.tests.test_scheduling_flow import test_schedule_natural_sentence_then_complete

if __name__ == "__main__":
    main()
    test_schedule_natural_sentence_then_complete()
