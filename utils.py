import json
import requests
import logging
from datetime import datetime
from flask import current_app

# Configure logging
logger = logging.getLogger(__name__)

def format_phone_for_api(phone):
    """Format phone number to 07XXXXXXXX format required by API"""
    # Ensure phone is a string
    phone = str(phone)

    # Remove any spaces, quotes or special characters
    phone = ''.join(c for c in phone if c.isdigit())

    # If it starts with 254, convert to local format
    if phone.startswith('254'):
        phone = '0' + phone[3:]

    # Make sure it starts with 0
    if not phone.startswith('0'):
        phone = '0' + phone

    # Ensure it's exactly 10 digits (07XXXXXXXX)
    if len(phone) > 10:
        phone = phone[:10]
    elif len(phone) < 10:
        logger.warning(f"Warning: Phone number {phone} is shorter than expected")

    logger.info(f"Original phone: {phone} -> Formatted for API: {phone}")
    return phone

def process_payment_callback(callback_data):
    """Process payment callback data - placeholder for compatibility"""
    logger.warning("Using deprecated process_payment_callback function - please update to use app.py functions directly")
    return True

def initiate_payment(username, amount, subscription_type, callback_url):
    """Initiate a payment request to the payment API - placeholder for compatibility"""
    logger.warning("Using deprecated initiate_payment function - please update to use app.py functions directly")
    
    # This is a dummy function now - just return success
    return f"demo_{datetime.now().strftime('%Y%m%d%H%M%S')}", "Payment completed successfully"
