import json
import requests
from datetime import datetime
from flask import current_app
from models import User, Payment, Transaction

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
        current_app.logger.warning(f"Warning: Phone number {phone} is shorter than expected")

    current_app.logger.info(f"Original phone: {phone} -> Formatted for API: {phone}")
    return phone

def process_payment_callback(callback_data):
    """Process payment callback data"""
    try:
        checkout_id = callback_data.get('CheckoutRequestID')
        if not checkout_id:
            current_app.logger.error("No checkout ID in callback data")
            return False

        # Get transaction
        transaction = Transaction.get(checkout_id)
        if not transaction:
            current_app.logger.error(f"Transaction not found for checkout ID: {checkout_id}")
            return False

        # Update transaction status
        reference = callback_data.get('reference', 'N/A')
        Transaction.update_status(checkout_id, 'completed', reference)

        # Get transaction details
        username = transaction['username']
        amount = transaction['amount']
        subscription_type = transaction['subscription_type']

        # Update payment record
        Payment.update_status(checkout_id, 'completed', reference)

        # Update word count
        words_to_add = 100 if subscription_type == 'basic' else 1000
        new_word_count = User.update_word_count(username, words_to_add)
        
        current_app.logger.info(f"Payment successful for {username}. Added {words_to_add} words. New balance: {new_word_count}")
        return True
    
    except Exception as e:
        current_app.logger.error(f"Error processing callback: {str(e)}")
        return False

def initiate_payment(username, amount, subscription_type, callback_url):
    """Initiate a payment request to the payment API"""
    # Get user data
    user = User.get_by_username(username)
    if not user:
        return None, "User not found"
    
    # Format phone number
    phone = format_phone_for_api(user['phone_number'])
    
    try:
        # Prepare API request
        headers = {
            'Authorization': f'Bearer {current_app.config["API_KEY"]}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'phone': phone,
            'amount': str(amount),
            'callback_url': callback_url
        }
        
        current_app.logger.info(f"Sending payment request with phone: {phone}, amount: {amount}")
        
        # Send payment request to API
        response = requests.post(
            f"{current_app.config['API_BASE_URL']}/request/stk",
            headers=headers,
            json=payload,
            timeout=30  # Timeout after 30 seconds
        )
        
        current_app.logger.info(f"API Response: {response.status_code} - {response.text}")
        
        # Process response
        if response.status_code == 200:
            response_data = response.json()
            
            # Check for successful response
            if response_data.get('message') == 'callback received successfully' and 'data' in response_data:
                data = response_data['data']
                checkout_id = data.get('CheckoutRequestID')
                reference = data.get('refference')  # Note: API uses "refference" with two f's
                
                # Create transaction record
                transaction_data = {
                    'checkout_id': checkout_id,
                    'username': username,
                    'amount': amount,
                    'phone': phone,
                    'subscription_type': subscription_type,
                    'status': 'completed',
                    'reference': reference
                }
                Transaction.create(checkout_id, transaction_data)
                
                # Create payment record
                Payment.create(
                    username,
                    amount,
                    subscription_type,
                    'completed',
                    reference,
                    checkout_id
                )
                
                # Update word count
                words_to_add = 100 if subscription_type == 'basic' else 1000
                User.update_word_count(username, words_to_add)
                
                return checkout_id, "Payment completed successfully"
                
            elif 'data' in response_data and 'CheckoutRequestID' in response_data['data']:
                # This is the case where we need to wait for callback
                checkout_id = response_data['data']['CheckoutRequestID']
                
                # Create transaction record
                transaction_data = {
                    'checkout_id': checkout_id,
                    'username': username,
                    'amount': amount,
                    'phone': phone,
                    'subscription_type': subscription_type,
                    'status': 'pending'
                }
                Transaction.create(checkout_id, transaction_data)
                
                # Create payment record
                Payment.create(
                    username,
                    amount,
                    subscription_type,
                    'pending',
                    'N/A',
                    checkout_id
                )
                
                return checkout_id, "Payment initiated, awaiting confirmation"
            else:
                # Handle error message from API
                error_msg = response_data.get('message', 'Unknown error')
                
                # Create failed payment record
                Payment.create(username, amount, subscription_type, 'failed')
                
                return None, f"Payment failed: {error_msg}"
        else:
            # Create failed payment record
            Payment.create(username, amount, subscription_type, 'failed')
            
            return None, f"Payment failed: Server returned status code {response.status_code}"
            
    except requests.exceptions.Timeout:
        # Create timeout payment record
        Payment.create(username, amount, subscription_type, 'timeout')
        
        return None, "Payment request timed out"
        
    except Exception as e:
        # Create error payment record
        Payment.create(username, amount, subscription_type, 'error')
        
        return None, f"Payment error: {str(e)}"
