# Lipia Subscription Payment System

This web application provides a subscription service with M-Pesa payment integration. Users can register, purchase word credits, and consume them as needed. The application is based on Flask and uses MongoDB as its database.

## Key Features

- User registration and authentication
- Subscription plans with different word limits
- M-Pesa payment integration
- Real-time payment status updates
- Word usage tracking

## Technical Architecture

The application follows a web-based architecture with the following components:

### Backend
- **Flask**: Web framework
- **MongoDB**: Database for storing user data, payments, and transactions
- **Flask-Login**: For user authentication
- **Flask-Bcrypt**: For password hashing
- **PyMongo**: For MongoDB integration

### Frontend
- **JavaScript**: For real-time payment status updates
- **Bootstrap**: For responsive UI design
- **HTML/CSS**: For page structure and styling

### Payment Processing
- **Asynchronous Payment Processing**: Uses background threads to process payments
- **Real-time Status Updates**: Client-side polling with JavaScript
- **Transaction Management**: MongoDB transactions for payment operations

## Payment Flow

The application implements a robust payment flow:

1. **Initiation**: User selects a subscription plan
2. **Queue Processing**: Payment request is added to a processing queue
3. **API Request**: The system sends a request to the M-Pesa API
4. **User Action**: User receives a prompt on their phone to authorize payment
5. **Callback Handling**: M-Pesa system sends callback to our application
6. **Status Updates**: Client-side JavaScript polls for payment status
7. **Transaction Completion**: System updates user's word count upon successful payment

## Handling Timeouts and Failures

- **Worker Timeouts**: Uses asynchronous processing to avoid gunicorn worker timeouts
- **Transaction Management**: MongoDB transactions ensure data consistency
- **Error Recovery**: Proper error handling and status tracking
- **Client-side Fallbacks**: UI provides options for users when timeouts occur

## MongoDB Schema

### Users Collection
- `username`: Unique identifier for the user
- `password`: Bcrypt-hashed password
- `phone_number`: User's phone number for M-Pesa payments
- `words_remaining`: Number of words available to the user
- `created_at`: User creation timestamp
- `last_login`: Last login timestamp

### Payments Collection
- `username`: Reference to the user
- `amount`: Payment amount
- `reference`: Payment reference number
- `checkout_id`: Unique payment identifier
- `subscription_type`: Type of subscription (basic/premium)
- `timestamp`: Payment timestamp
- `status`: Payment status (pending/completed/failed/etc.)

### Transactions Collection
- `checkout_id`: Unique transaction identifier
- `real_checkout_id`: M-Pesa generated checkout ID (if different)
- `username`: Reference to the user
- `amount`: Transaction amount
- `subscription_type`: Type of subscription (basic/premium)
- `timestamp`: Transaction initiation timestamp
- `updated_at`: Last update timestamp
- `status`: Transaction status (queued/processing/completed/failed/etc.)
- `error`: Error message if applicable
- `reference`: Payment reference number from M-Pesa

## Deployment

The application is configured for deployment on Railway.app with:

- **Gunicorn**: Web server with increased timeouts (120s) for payment processing
- **MongoDB Atlas**: Cloud database for production use
- **Environment Variables**: Configuration via environment variables

## Security Considerations

- **Password Hashing**: Using bcrypt for secure password storage
- **Transaction Validation**: Verifying user ownership of transactions
- **Error Logging**: Comprehensive error handling and logging
- **MongoDB Connection**: Secure connection to MongoDB Atlas

## Best Practices Implemented

1. **Asynchronous Payment Processing**: Using a queue and background worker
2. **Proper Error Handling**: Comprehensive try/except blocks
3. **Real-time Updates**: Client-side polling for status updates
4. **Timeout Management**: Proper handling of timeouts in web requests
5. **Transaction Atomicity**: MongoDB transactions for data consistency
6. **Graceful Degradation**: Fallback mechanisms when services are unavailable
7. **Clean Separation of Concerns**: Payment processing logic in separate module

## Development Setup

1. Clone the repository
2. Create a virtual environment: `python -m venv venv`
3. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - Unix/Mac: `source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Set up environment variables (see .env.example)
6. Run the application: `flask run`

## Environment Variables

- `SECRET_KEY`: Flask secret key
- `MONGO_URI`: MongoDB connection URI
- `API_KEY`: M-Pesa API key
- `API_BASE_URL`: M-Pesa API base URL
- `CALLBACK_URL`: Public URL for payment callbacks
- `FLASK_DEBUG`: Enable debug mode (True/False)
