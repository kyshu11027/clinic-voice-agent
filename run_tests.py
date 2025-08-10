#!/usr/bin/env python3
"""
Test runner for the Clinic Voice Agent
"""

import sys
import os

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from tests.test_setup import main

if __name__ == "__main__":
    main()
