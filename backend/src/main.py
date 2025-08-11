import os
import logging
from fastapi import FastAPI, Request, Form
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
from twilio.twiml.voice_response import VoiceResponse, Gather
from .call_flow import CallFlowManager
from .models import CallStep

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")))
logger = logging.getLogger(__name__)

app = FastAPI(title="Clinic Voice Agent", version="1.0.0")

# Initialize call flow manager
call_flow_manager = CallFlowManager()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "clinic-voice-agent"}

@app.post("/voice")
async def handle_incoming_call(request: Request):
    """Handle incoming voice calls from Twilio"""
    logger.info("Received incoming call")
    
    # Create TwiML response
    response = VoiceResponse()
    
    # Greet the caller
    response.say("Hello! Thank you for calling Juntendo clinic. How can I help you today?")
    
    # Gather speech input
    gather = Gather(
        input='speech',
        action='/voice/handle',
        method='POST',
        speech_timeout='auto',
        language='en-US'
    )
    response.append(gather)
    
    # Fallback if no input
    response.say("I didn't hear anything. Please call back and let me know how I can help you.")
    response.hangup()
    
    return PlainTextResponse(str(response), media_type="application/xml")

@app.post("/voice/handle")
async def handle_speech_input(
    request: Request,
    SpeechResult: str = Form(None),
    CallSid: str = Form(None)
):
    """Handle speech input from the caller"""
    logger.info(f"Received speech input: {SpeechResult}")
    
    response = VoiceResponse()
    
    if not SpeechResult:
        response.say("I didn't catch that. Could you please repeat what you'd like to do?")
        response.hangup()
        return PlainTextResponse(str(response), media_type="application/xml")
    
    # Process speech input through call flow manager
    try:
        response_message = call_flow_manager.process_speech_input(CallSid, SpeechResult)
        response.say(response_message)
        
        # Decide whether to continue listening based on whether state still exists
        state_exists = CallSid in call_flow_manager.call_states
        if state_exists:
            gather = Gather(
                input='speech',
                action='/voice/handle',
                method='POST',
                speech_timeout='auto',
                language='en-US'
            )
            response.append(gather)
            # Fallback if no input
            response.say("I didn't hear anything. Please call back and let me know how I can help you.")
            response.hangup()
        else:
            # State was cleared (e.g., after successful booking); end the call
            response.hangup()
        
    except Exception as e:
        logger.error(f"Error processing speech input: {e}")
        response.say("I'm sorry, I'm having trouble understanding right now. Please call back in a few minutes.")
        response.hangup()
    
    return PlainTextResponse(str(response), media_type="application/xml")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
