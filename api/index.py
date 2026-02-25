"""Vercel entry point — imports the Flask app from the project root."""
import sys
import os

# Add project root to PYTHONPATH so `src` package is resolvable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web_interview import app  # noqa: F401  (Vercel detects `app`)
