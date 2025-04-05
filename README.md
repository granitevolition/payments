# Lipia Subscription Service

A web-based subscription management system for the Andikar AI service, enabling users to purchase and manage word subscriptions.

## Overview

This application provides a complete subscription management solution for the Andikar AI text humanization service. It allows users to:

- Create and manage user accounts
- Purchase word subscriptions via M-PESA
- Track word usage and payment history
- Consume words from their account balance

## Tech Stack

- **Backend**: Flask (Python web framework)
- **Database**: MongoDB
- **Frontend**: HTML, CSS, JavaScript
- **Payment Processing**: Integrated with Lipia API for M-PESA payments
- **Deployment**: Ready for Heroku, Railway, or any platform supporting Python

## Features

### User Management
- User registration and authentication
- Secure password handling with bcrypt
- Session management

### Subscription System
- Multiple subscription tiers (Basic and Premium)
- Payment processing via M-PESA
- Real-time payment status tracking
- Payment history

### Word Usage
- Track word balance
- Consume words from balance
- Word usage validation

### API Integration
- Integration with Lipia API for payment processing
- Callback handling for payment confirmation

## Project Structure

- `app.py` - Main Flask application
- `config.py` - Application configuration
- `models.py` - MongoDB models for users, payments, and transactions
- `utils.py` - Utility functions for payments and API integration
- `forms.py` - Form validation classes
- `templates/` - HTML templates
- `static/` - CSS and JavaScript assets

## Setup Instructions

### Prerequisites
- Python 3.8 or higher
- MongoDB (local or cloud instance)
- M-PESA integration (via Lipia API)

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/granitevolition/payments.git
   cd payments
   ```

2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\\Scripts\\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   ```
   cp .env.example .env
   ```
   Edit `.env` file to set the appropriate values for your environment.

5. Start the application:
   ```
   flask run
   ```
   Or for production:
   ```
   gunicorn app:app
   ```

## MongoDB Configuration

This application uses MongoDB as its database. The connection string is configured in the `.env` file:

```
MONGO_URI=mongodb+srv://edgarmaina003:<db_password>@oldtrafford.id96k.mongodb.net/?retryWrites=true&w=majority&appName=OldTrafford
```

Make sure to replace `<db_password>` with your actual password.

## Database Collections

The application uses the following MongoDB collections:

1. **users** - User accounts and word balances
2. **payments** - Payment records
3. **transactions** - Transaction tracking for payments

## API Integration

The application integrates with the Lipia API for M-PESA payment processing. The API base URL and key are configured in the `.env` file:

```
API_BASE_URL=https://lipia-api.kreativelabske.com/api
API_KEY=your_api_key_here
```

## Deployment

The application includes a `Procfile` for easy deployment to platforms like Heroku or Railway.

## Security Considerations

- User passwords are hashed using bcrypt
- API keys are stored in environment variables
- Session management is handled securely
- Form validation prevents common attacks

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

[MIT](https://choosealicense.com/licenses/mit/)
