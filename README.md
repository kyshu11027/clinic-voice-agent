# Clinic Voice Agent

An AI-powered voice agent that answers calls and schedules/reschedules appointments for a chiropractic & acupuncture clinic with multiple locations and doctors.

## Features

- **Voice Call Handling**: Receives incoming calls via Twilio
- **Natural Language Understanding**: Uses OpenAI GPT-4 to understand caller intent
- **Appointment Scheduling**: Books appointments with available doctors
- **Multi-location Support**: Handles 2 clinic locations (Arlington Heights and Highland Park)
- **Multiple Service Types**: Chiropractic, Acupuncture, Massage, and Consultation
- **State Management**: Maintains conversation context throughout the call

## Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Twilio    │───▶│  FastAPI    │───▶│   OpenAI    │
│   Voice     │    │   Backend   │    │     NLU     │
└─────────────┘    └─────────────┘    └─────────────┘
                          │
                          ▼
                   ┌─────────────┐
                   │   Google    │
                   │  Calendar   │
                   └─────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (optional)
- Twilio account
- OpenAI API key
- Google Calendar API credentials (optional for MVP)

### 1. Clone and Setup

```bash
git clone <repository-url>
cd clinic-voice-agent
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Environment Configuration

Create a `.env` file with your credentials:

```bash
# Twilio Configuration
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=your_twilio_phone_number

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key

# Google Calendar Configuration (optional for MVP)
GOOGLE_CALENDAR_CREDENTIALS_JSON={"type": "service_account", ...}

# App Configuration
APP_ENV=development
LOG_LEVEL=INFO
```

### 4. Run the Application

#### Option A: Direct Python
```bash
python main.py
```

#### Option B: Using Uvicorn
```bash
cd backend && uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

#### Option C: Using Docker
```bash
cd backend/deployment && docker-compose up --build
```

### 5. Test the Application

1. **Health Check**: Visit `http://localhost:8000/health`
2. **Voice Endpoint**: `http://localhost:8000/voice` (POST)
3. **Run Tests**: `python run_tests.py`

### 6. Configure Twilio

1. Go to your Twilio Console
2. Navigate to Phone Numbers → Manage → Active numbers
3. Select your phone number
4. Set the webhook URL for incoming calls to: `https://your-domain.com/voice`
5. Set the HTTP method to POST

## Development

### Project Structure

```
clinic-voice-agent/
├── main.py                 # Main entry point
├── run_tests.py            # Test runner
├── activate.sh             # Development startup script
├── backend/
│   ├── src/                # Source code
│   │   ├── __init__.py
│   │   ├── main.py         # FastAPI application
│   │   ├── models.py       # Pydantic data models
│   │   ├── calendar_service.py  # Google Calendar integration
│   │   ├── nlu.py          # Natural Language Understanding
│   │   ├── call_flow.py    # Conversation state management
│   │   └── data/
│   │       └── clinic.json # Clinic configuration data
│   ├── tests/              # Test files
│   │   └── test_setup.py   # Setup verification tests
│   ├── deployment/         # Deployment configuration
│   │   ├── Dockerfile      # Docker configuration
│   │   └── docker-compose.yml # Docker Compose configuration
│   └── requirements.txt    # Python dependencies
└── README.md              # This file
```

### Key Components

#### 1. Data Models (`models.py`)
- `ServiceType`: Enum for service types (chiropractic, acupuncture, etc.)
- `Location`: Enum for clinic locations
- `Doctor`: Doctor information and availability
- `Appointment`: Appointment data structure
- `CallState`: Conversation state management

#### 2. Calendar Service (`calendar_service.py`)
- Manages Google Calendar integration
- Generates available appointment slots
- Creates and reschedules appointments
- For MVP: Uses mock data generation

#### 3. NLU Processor (`nlu.py`)
- Uses OpenAI GPT-4 for intent recognition
- Extracts entities (service type, location, doctor, etc.)
- Fallback to keyword matching if OpenAI unavailable

#### 4. Call Flow Manager (`call_flow.py`)
- Manages conversation state
- Routes through different conversation steps
- Handles scheduling and rescheduling flows

### Testing

#### Local Testing with ngrok

1. Install ngrok: `brew install ngrok` (macOS) or download from ngrok.com
2. Start your application: `uvicorn main:app --reload`
3. Expose your local server: `ngrok http 8000`
4. Use the ngrok URL as your Twilio webhook: `https://your-ngrok-url.ngrok.io/voice`

#### Manual Testing

You can test the voice endpoints using curl:

```bash
# Test health endpoint
curl http://localhost:8000/health

# Test voice endpoint (simulates Twilio webhook)
curl -X POST http://localhost:8000/voice \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "CallSid=test123"
```

## Deployment

### Railway (Recommended for MVP)

1. Install Railway CLI: `npm install -g @railway/cli`
2. Login: `railway login`
3. Initialize: `railway init`
4. Deploy: `railway up`

### Render

1. Connect your GitHub repository to Render
2. Create a new Web Service
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

### Environment Variables

Make sure to set all required environment variables in your deployment platform:

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_PHONE_NUMBER`
- `OPENAI_API_KEY`
- `GOOGLE_CALENDAR_CREDENTIALS_JSON` (optional)

## MVP Limitations

For the MVP version:

1. **Appointments**: Stored in memory (not persisted to Google Calendar)
2. **Patient Data**: Limited patient information collection
3. **Rescheduling**: Basic acknowledgment (not fully implemented)
4. **Error Handling**: Basic error responses
5. **Authentication**: No patient authentication

## Future Enhancements

1. **Google Calendar Integration**: Full calendar sync
2. **Patient Database**: Store patient information
3. **SMS Confirmations**: Send appointment confirmations
4. **Advanced NLU**: Better entity extraction
5. **Multi-language Support**: Spanish and other languages
6. **Analytics**: Call analytics and reporting
7. **Admin Dashboard**: Web interface for management

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support, please contact the development team or create an issue in the repository.
