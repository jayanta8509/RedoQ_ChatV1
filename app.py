"""
FastAPI FlightAware Chatbot API
Provides REST endpoints for FlightAware aviation data using RAG with Pinecone

Endpoints:
- POST /chat - Main chat endpoint with user_id and query
- GET /health - Health check endpoint
- POST /chat/agent - Chat with agent mode for complex queries
- DELETE /chat/{user_id} - Clear conversation history for a user
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from contextlib import asynccontextmanager
import logging
import os
from datetime import datetime
import uvicorn

# Import our RAG functions
from rag import initialize_rag_system, get_response, get_conversation_summary, clear_conversation

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global system state
system_initialized = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown"""
    global system_initialized
    try:
        logger.info("🚀 Starting FlightAware RAG Chatbot API...")
        initialize_rag_system()
        system_initialized = True
        logger.info("✅ FlightAware RAG System initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize system: {e}")
        system_initialized = False
        # Don't raise here - let the API start but handle errors in endpoints
    
    yield
    
    # Cleanup on shutdown
    logger.info("🛑 Shutting down FlightAware RAG API...")

# Initialize FastAPI app
app = FastAPI(
    title="FlightAware RAG Chatbot API",
    description="AI-powered FlightAware aviation intelligence using Retrieval Augmented Generation",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure as needed for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for request/response
class ChatRequest(BaseModel):
    user_id: str = Field(..., description="Unique identifier for the user", min_length=1, max_length=100)
    query: str = Field(..., description="User's message/question", min_length=1, max_length=2000)
    use_agent: bool = Field(True, description="Whether to use agent mode for complex queries")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "user_id": "user123",
                "query": "How does FlightAware track flights globally?",
                "use_agent": True
            }
        }
    }

class ChatResponse(BaseModel):
    user_id: str = Field(..., description="User identifier")
    query: str = Field(..., description="Original user query")
    response: str = Field(..., description="AI assistant response")
    mode: str = Field(..., description="Processing mode used (assistant/agent/error)")
    data_source: Optional[str] = Field(None, description="Data source used for retrieval (json/pdf/both/none)")
    source_urls: Optional[list] = Field(default_factory=list, description="List of source URLs from retrieved documents")
    timestamp: float = Field(..., description="Unix timestamp of response")
    error: Optional[str] = Field(None, description="Error message if any")
    status_code: int = Field(200, description="HTTP status code")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "user_id": "user123",
                "query": "How does FlightAware track flights globally?",
                "response": "FlightAware tracks flights globally using a comprehensive network of data sources...",
                "mode": "assistant",
                "data_source": "json",
                "source_urls": ["https://www.flightaware.com/about/", "https://www.flightaware.com/commercial/"],
                "timestamp": 1640995200.0,
                "error": None,
                "status_code": 200
            }
        }
    }

class HealthResponse(BaseModel):
    status: str
    message: str
    timestamp: float
    pinecone_connected: bool
    models_loaded: bool
    status_code: int = Field(200, description="HTTP status code")

class ConversationClearResponse(BaseModel):
    user_id: str
    message: str
    timestamp: float
    
class ConversationSummaryResponse(BaseModel):
    user_id: str
    summary: str
    timestamp: float
    status_code: int = Field(200, description="HTTP status code")


# Health check endpoint
@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint to verify API and system status
    """
    try:
        status = "healthy" if system_initialized else "degraded"
        
        return HealthResponse(
            status=status,
            message="FlightAware RAG API is running",
            timestamp=datetime.now().timestamp(),
            pinecone_connected=system_initialized,
            models_loaded=system_initialized,
            status_code=200
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            message=f"Health check failed: {str(e)}",
            timestamp=datetime.now().timestamp(),
            pinecone_connected=False,
            models_loaded=False,
            status_code=500
        )

# Main chat endpoint
@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat_endpoint(request: ChatRequest):
    """
    Main chat endpoint for FlightAware aviation intelligence
    
    **Parameters:**
    - **user_id**: Unique identifier for the user (maintains conversation context)
    - **query**: User's message or question about FlightAware
    - **use_agent**: Set to true for complex queries requiring multi-step research (default: false)
    
    **Features:**
    - User-specific conversation memory
    - Retrieval from FlightAware JSON knowledge base
    - Expert aviation intelligence responses
    - Structured, authoritative answers
    - Data source tracking (json)
    """
    if not system_initialized:
        raise HTTPException(
            status_code=503, 
            detail="FlightAware system is not initialized. Please check server logs."
        )
    
    try:
        logger.info(f"Processing chat request for user {request.user_id}")
        
        # Get response using function-based approach
        response_data = get_response(
            message=request.query,
            user_id=request.user_id,
            use_agent=request.use_agent
        )
        
        # Log data source usage for monitoring
        if response_data.get("data_source"):
            logger.info(f"Data source used: {response_data.get('data_source')} for user {request.user_id}")
        
        return ChatResponse(**response_data)
        
    except Exception as e:
        logger.error(f"Error processing chat request: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing your message: {str(e)}"
        )


# Run the application
if __name__ == "__main__":
    # Get port from environment or default to 8000
    port = int(os.getenv("PORT", 8000))
    
    # Run with uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=True,  # Set to False in production
        log_level="info"
    )
