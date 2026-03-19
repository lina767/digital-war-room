"""
Rate limiting for API routes. Uses slowapi with key_func = client IP.
Mount limiter on app in main.py; apply @limiter.limit("N/minute") on routes.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
