#!/usr/bin/env python3
"""
FastAPI Endpoint for Twilio WhatsApp Announcement Processor
Provides a REST API endpoint to trigger the announcement processing
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import sys
import os

# Import the main function from twilio_whatsapp_processor
from twilio_whatsapp_processor import process_latest_announcement, validate_environment_variables

# Initialize FastAPI app
app = FastAPI(
    title="FinVarta WhatsApp Processor API",
    description="API endpoint to process and send corporate announcements via WhatsApp",
    version="1.0.0"
)

# Request model for the endpoint
class ProcessRequest(BaseModel):
    use_sample_data: Optional[bool] = False

# Response model
class ProcessResponse(BaseModel):
    success: bool
    message: str
    details: Optional[str] = None

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "FinVarta WhatsApp Processor API",
        "version": "1.0.0",
        "endpoints": {
            "POST /process": "Process latest announcement and send via WhatsApp",
            "GET /health": "Health check endpoint"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "FinVarta WhatsApp Processor"}

@app.post("/process", response_model=ProcessResponse)
async def process_announcement(request: ProcessRequest):
    """
    Process the latest corporate announcement and send via WhatsApp
    
    Args:
        request: ProcessRequest containing optional parameters
        
    Returns:
        ProcessResponse with success status and details
    """
    try:
        # Validate environment variables first
        if not validate_environment_variables():
            raise HTTPException(
                status_code=500, 
                detail="Environment variables not properly configured. Check your .env file."
            )
        
        # Process the announcement
        success = process_latest_announcement(
            cookie_header=os.getenv("SCREENER_COOKIE_HEADER"),
            use_sample_data=request.use_sample_data
        )
        
        if success:
            return ProcessResponse(
                success=True,
                message="Announcement processed successfully",
                details="WhatsApp message sent to configured recipients"
            )
        else:
            return ProcessResponse(
                success=False,
                message="Failed to process announcement",
                details="Check logs for specific error details"
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    
    # Run the FastAPI server
    uvicorn.run(
        "fastapi_endpoint:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
