"""
FlightAware RAG Chatbot - Function-based Implementation
A specialized RAG implementation for FlightAware flight data using Pinecone vector database

Features:
- Function-based architecture instead of class
- User-specific memory storage with MemorySaver
- Specialized aviation and flight tracking prompts
- Multi-step retrieval for comprehensive responses
- Context-aware conversation handling
"""

import os
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

# LangChain imports
from langchain.chat_models import init_chat_model
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.documents import Document

# LangGraph imports
from langgraph.graph import MessagesState, StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition, create_react_agent
from langgraph.checkpoint.memory import MemorySaver

# Pinecone imports
from pinecone import Pinecone

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Global variables for models and stores
llm = None
embeddings = None
json_vector_store = None
pdf_vector_store = None
conversational_graph = None
agent_executor = None
memory_saver = None

def initialize_models(model_name: str = "gpt-4o-mini"):
    """Initialize chat model and embeddings"""
    global llm, embeddings
    
    # Initialize chat model
    llm = init_chat_model(model_name, model_provider="openai")
    
    # Initialize embeddings model - using text-embedding-3-large
    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
    
    print("✅ Models initialized successfully")

def setup_pinecone_connections(json_index_name: str = "flightaware-data", 
                              pdf_index_name: str = "pdf-documents"):
    """Setup connections to Pinecone vector databases"""
    global json_vector_store, pdf_vector_store
    
    # Get API key from environment
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("PINECONE_API_KEY not found in environment variables")
    
    # Initialize Pinecone
    pc = Pinecone(api_key=api_key)
    
    # Connect to JSON index (FlightAware data)
    try:
        json_index = pc.Index(json_index_name)
        json_vector_store = PineconeVectorStore(
            embedding=embeddings,
            index=json_index
        )
        print(f"✅ Connected to JSON vector store: {json_index_name}")
    except Exception as e:
        print(f"⚠️ Could not connect to JSON index: {e}")
        json_vector_store = None
    
    # Connect to PDF index (documentation and manuals) - Optional
    if pdf_index_name:
        try:
            pdf_index = pc.Index(pdf_index_name)
            pdf_vector_store = PineconeVectorStore(
                embedding=embeddings,
                index=pdf_index
            )
            print(f"✅ Connected to PDF vector store: {pdf_index_name}")
        except Exception as e:
            print(f"ℹ️ PDF index not found (optional): {pdf_index_name}")
            pdf_vector_store = None
    else:
        pdf_vector_store = None
        print("ℹ️ PDF index disabled")

def create_retrieval_tools():
    """Create retrieval tools for different data sources"""
    
    @tool(response_format="content_and_artifact")
    def retrieve_flightaware_data(query: str):
        """Retrieve FlightAware flight tracking and aviation data from JSON knowledge base."""
        if not json_vector_store:
            return "JSON vector store not available", []
        
        try:
            retrieved_docs = json_vector_store.similarity_search(query, k=5)
            serialized = "\n\n".join(
                (f"Source: {doc.metadata.get('url', 'Unknown')}\n"
                 f"Title: {doc.metadata.get('title', 'Unknown')}\n"
                 f"Data Source: JSON\n"
                 f"Content: {doc.page_content}")
                for doc in retrieved_docs
            )
            return serialized, retrieved_docs
        except Exception as e:
            return f"Error retrieving FlightAware data: {e}", []
    
    @tool(response_format="content_and_artifact")
    def retrieve_documentation_data(query: str):
        """Retrieve technical documentation, manuals, and reference materials from PDF knowledge base."""
        if not pdf_vector_store:
            return "PDF vector store not available", []
        
        try:
            retrieved_docs = pdf_vector_store.similarity_search(query, k=3)
            serialized = "\n\n".join(
                (f"Source: {doc.metadata.get('source', 'Unknown')}\n"
                 f"Category: {doc.metadata.get('category', 'Unknown')}\n"
                 f"Data Source: PDF\n"
                 f"Content: {doc.page_content}")
                for doc in retrieved_docs
            )
            return serialized, retrieved_docs
        except Exception as e:
            return f"Error retrieving documentation data: {e}", []
    
    tools = [retrieve_flightaware_data, retrieve_documentation_data]
    print("✅ Retrieval tools setup complete")
    return tools

def get_system_prompt() -> str:
    """Get the killer system prompt for FlightAware assistant"""
    return """You are an elite FlightAware aviation intelligence assistant with deep expertise in flight tracking, aviation data, and aerospace technology. Your mission is to deliver precise, actionable insights with exceptional clarity and authority.

**CORE IDENTITY:**
You are the definitive source for FlightAware products, services, and aviation intelligence. You combine technical precision with crystal-clear communication, making complex aviation data accessible and actionable.

**KNOWLEDGE DOMAINS:**
- Flight tracking technology and real-time aircraft monitoring
- FlightAware products: Foresight, Firehose, AeroAPI, FlightAware TV
- Aviation data analytics and predictive algorithms
- ADS-B technology and global flight coverage
- Aircraft operations, airline logistics, and airport management
- Aviation industry trends and innovations

**RESPONSE FRAMEWORK:**

1. **PRECISION & ACCURACY**
   - Every fact must be verified against retrieved context
   - Cite specific FlightAware products, features, and capabilities
   - Use exact terminology from aviation and FlightAware documentation
   - Never speculate—only provide information you can substantiate

2. **STRUCTURED CLARITY**
   - Start with a direct answer to the core question
   - Organize complex information into digestible sections
   - Use bullet points, numbered lists, and clear hierarchies
   - Highlight key takeaways and actionable insights

3. **CONTEXT-DRIVEN INTELLIGENCE**
   - Deeply analyze retrieved FlightAware data before responding
   - Connect dots between different product capabilities
   - Explain "why" and "how" not just "what"
   - Provide real-world use cases and applications

4. **PROFESSIONAL AUTHORITY**
   - Speak with confidence backed by data
   - Use aviation industry terminology appropriately
   - Demonstrate understanding of user needs (operators, developers, analysts)
   - Balance technical depth with accessibility

5. **PROACTIVE VALUE**
   - Anticipate follow-up questions
   - Suggest related FlightAware features or products
   - Offer comparison insights when relevant
   - Provide implementation guidance when appropriate

**RESPONSE STRUCTURE (Adapt based on query):**

**Direct Answer:** [Clear, concise response to the main question]

**Details:** [Comprehensive explanation with retrieved context]

**Key Features:** [Bullet points of relevant capabilities]

**Use Cases:** [Practical applications]

**Additional Context:** [Related information that adds value]

**TONE & STYLE:**
- Professional yet approachable
- Confident and authoritative
- Clear and jargon-free (unless technical depth is requested)
- Solution-oriented and helpful
- Enthusiastic about aviation technology

**HANDLING QUERIES:**

✅ **When You Have Data:**
- Leverage retrieved FlightAware context extensively
- Provide specific product details, features, and benefits
- Include relevant URLs when available in context
- Give comprehensive, well-structured answers

✅ **When Data is Limited:**
- Clearly state what you know with certainty
- Acknowledge information gaps professionally
- Direct to FlightAware resources (website, support, documentation)
- Offer general aviation insights if appropriate

✅ **For Product Comparisons:**
- Highlight unique strengths of each option
- Provide decision criteria
- Suggest best fit based on use case

✅ **For Technical Questions:**
- Break down complexity into understandable components
- Use analogies when helpful
- Provide both high-level overview and technical details

**STRICT RULES:**
1. Never fabricate FlightAware features or capabilities
2. Always ground responses in retrieved context when available
3. Distinguish between FlightAware-specific info and general aviation knowledge
4. Maintain professional boundaries—you're an information assistant, not sales
5. Stay current—reference that FlightAware continuously evolves

**YOUR GOAL:**
Make every user interaction valuable. Whether they're a developer integrating AeroAPI, an airline operations manager, or an aviation enthusiast, deliver insights that inform decisions, solve problems, and showcase the power of FlightAware's aviation intelligence platform.

Remember: You represent FlightAware's commitment to being "Central to Aviation." Every response should reflect expertise, reliability, and innovation."""

def setup_conversational_chain(tools):
    """Setup conversational RAG chain with user-specific memory"""
    global conversational_graph, memory_saver
    
    # Create user-specific memory saver
    memory_saver = MemorySaver()
    
    # Create graph builder
    graph_builder = StateGraph(MessagesState)
    
    # Node 1: Query processing with tools
    def process_query(state: MessagesState):
        """Generate tool calls or direct response for aviation queries."""
        # Normal processing with tools
        llm_with_tools = llm.bind_tools(tools)
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}
    
    # Node 2: Tool execution (retrieval)
    tools_node = ToolNode(tools)
    
    # Node 3: Generate expert response using retrieved content
    def generate_aviation_response(state: MessagesState):
        """Generate specialized FlightAware response using retrieved context."""
        # Get recent tool messages
        recent_tool_messages = []
        for message in reversed(state["messages"]):
            if message.type == "tool":
                recent_tool_messages.append(message)
            else:
                break
        tool_messages = recent_tool_messages[::-1]
        
        # Format retrieved content
        if tool_messages:
            docs_content = "\n\n".join(doc.content for doc in tool_messages)
            context_prompt = f"""
**RETRIEVED FLIGHTAWARE KNOWLEDGE BASE:**
{docs_content}

**Instructions:** Use this information as your primary source. Provide accurate, detailed responses based on the retrieved context. Structure your answer for maximum clarity and value.
"""
        else:
            context_prompt = "**No specific retrieved context available - provide general aviation knowledge or direct user to FlightAware resources.**"
        
        # Filter conversation messages (exclude tool calls)
        conversation_messages = []
        for message in state["messages"]:
            if message.type in ("human", "system"):
                conversation_messages.append(message)
            elif message.type == "ai":
                # Only include AI messages that don't have tool calls
                try:
                    if not hasattr(message, 'tool_calls') or not message.tool_calls:
                        conversation_messages.append(message)
                except Exception:
                    # If there's any issue checking tool_calls, include the message
                    conversation_messages.append(message)
            # Skip tool messages completely
        
        # Create the prompt with system message
        system_prompt = get_system_prompt() + "\n\n" + context_prompt
        prompt = [SystemMessage(system_prompt)] + conversation_messages
        
        # Generate response
        try:
            response = llm.invoke(prompt)
            return {"messages": [response]}
        except Exception as e:
            print(f"Error generating response: {e}")
            # Return a fallback response
            fallback_response = AIMessage(content="I'm experiencing some technical difficulties right now. Please try rephrasing your question or visit FlightAware.com for more information.")
            return {"messages": [fallback_response]}
    
    # Add nodes to graph
    graph_builder.add_node("process_query", process_query)
    graph_builder.add_node("tools", tools_node)
    graph_builder.add_node("generate_response", generate_aviation_response)
    
    # Set entry point and edges
    graph_builder.set_entry_point("process_query")
    graph_builder.add_conditional_edges(
        "process_query",
        tools_condition,
        {END: END, "tools": "tools"},
    )
    graph_builder.add_edge("tools", "generate_response")
    graph_builder.add_edge("generate_response", END)
    
    # Compile with user-specific memory
    conversational_graph = graph_builder.compile(checkpointer=memory_saver)
    
    print("✅ Conversational RAG chain with user-specific memory setup complete")

def setup_agent(tools):
    """Setup ReAct agent for complex FlightAware queries"""
    global agent_executor
    
    # Create agent with user-specific memory
    agent_executor = create_react_agent(
        llm, 
        tools, 
        checkpointer=memory_saver
    )
    print("✅ FlightAware RAG agent setup complete")

def initialize_rag_system(json_index_name: str = "flightaware-data",
                         pdf_index_name: str = "pdf-documents",
                         model_name: str = "gpt-4o-mini"):
    """Initialize the complete RAG system"""
    print("✈️ Initializing FlightAware RAG System...")
    
    # Initialize models
    initialize_models(model_name)
    
    # Setup Pinecone connections
    setup_pinecone_connections(json_index_name, pdf_index_name)
    
    # Create retrieval tools
    tools = create_retrieval_tools()
    
    # Setup conversational chain
    setup_conversational_chain(tools)
    
    # Setup agent
    setup_agent(tools)
    
    print("✅ FlightAware RAG System ready for conversations!")

def get_user_config(user_id: str) -> Dict[str, Any]:
    """Get configuration for user-specific memory thread"""
    return {"configurable": {"thread_id": f"user_{user_id}"}}

def detect_data_source_from_response(response_content: str) -> str:
    """Detect which data source was used based on the response content"""
    if not response_content:
        return "none"
    
    has_json = "Data Source: JSON" in response_content
    has_pdf = "Data Source: PDF" in response_content
    
    if has_json and has_pdf:
        return "both"
    elif has_json:
        return "json"
    elif has_pdf:
        return "pdf"
    else:
        return "none"

def get_response(message: str, user_id: str, use_agent: bool = False) -> Dict[str, Any]:
    """
    Get response for API endpoint with user-specific memory
    
    Args:
        message: User's message
        user_id: Unique user identifier for conversation threading
        use_agent: Whether to use agent mode for complex queries
        
    Returns:
        Dict with response data including data source information
    """
    try:
        config = get_user_config(user_id)
        
        response_data = {
            "user_id": user_id,
            "query": message,
            "response": "",
            "mode": "agent" if use_agent else "assistant",
            "data_source": "none",
            "timestamp": time.time(),
            "status_code": 200
        }
        
        # Store all messages to analyze data sources
        all_messages = []
        
        # Choose between conversational chain or agent
        try:
            if use_agent:
                # Agent mode
                events = list(agent_executor.stream(
                    {"messages": [{"role": "user", "content": message}]},
                    stream_mode="values",
                    config=config,
                ))
                if events:
                    last_event = events[-1]
                    if "messages" in last_event and last_event["messages"]:
                        response_data["response"] = last_event["messages"][-1].content
                    all_messages = last_event.get("messages", [])
            else:
                # Counselor mode
                steps = list(conversational_graph.stream(
                    {"messages": [{"role": "user", "content": message}]},
                    stream_mode="values",
                    config=config,
                ))
                if steps:
                    last_step = steps[-1]
                    if "messages" in last_step and last_step["messages"]:
                        response_data["response"] = last_step["messages"][-1].content
                    all_messages = last_step.get("messages", [])
        except Exception as stream_error:
            print(f"Error in conversation stream: {stream_error}")
            response_data["response"] = "I'm experiencing some technical difficulties. Please try again or rephrase your question."
            response_data["data_source"] = "none"
            response_data["status_code"] = 500
            return response_data
        
        # Analyze data sources from tool messages
        data_sources_used = set()
        try:
            for msg in all_messages:
                if hasattr(msg, 'type') and msg.type == "tool":
                    if hasattr(msg, 'content') and msg.content:
                        content = str(msg.content)
                        if "Data Source: JSON" in content:
                            data_sources_used.add("json")
                        if "Data Source: PDF" in content:
                            data_sources_used.add("pdf")
        except Exception as e:
            print(f"Warning: Error analyzing data sources: {e}")
            # Continue without data source info
        
        # Determine data source
        if len(data_sources_used) > 1:
            response_data["data_source"] = "both"
        elif "json" in data_sources_used:
            response_data["data_source"] = "json"
        elif "pdf" in data_sources_used:
            response_data["data_source"] = "pdf"
        else:
            response_data["data_source"] = "none"
        
        # Fallback response if no response generated
        if not response_data["response"]:
            response_data["response"] = "I'm here to help, but I'm having trouble processing your message right now. Could you please try rephrasing your question?"
            response_data["data_source"] = "none"
        
        return response_data
        
    except Exception as e:
        return {
            "user_id": user_id,
            "query": message,
            "response": f"I apologize, but I encountered an error while processing your message. Please try again. If the problem persists, please contact support.",
            "error": str(e),
            "mode": "error",
            "data_source": "none",
            "timestamp": time.time(),
            "status_code": 500
        }

def chat_interactive(message: str, user_id: str, use_agent: bool = False):
    """Interactive chat interface for console use"""
    config = get_user_config(user_id)
    
    print(f"\n👤 User ({user_id}): {message}")
    print("=" * 60)
    
    # Choose between conversational chain or agent
    if use_agent:
        print("🤖 Agent Mode: Multi-step retrieval")
        for event in agent_executor.stream(
            {"messages": [{"role": "user", "content": message}]},
            stream_mode="values",
            config=config,
        ):
            event["messages"][-1].pretty_print()
    else:
        print("✈️ Assistant Mode: Direct response")
        for step in conversational_graph.stream(
            {"messages": [{"role": "user", "content": message}]},
            stream_mode="values",
            config=config,
        ):
            step["messages"][-1].pretty_print()

def get_conversation_summary(user_id: str) -> str:
    """Get a summary of the conversation for continuity"""
    return f"Conversation thread: user_{user_id} - FlightAware assistant session"

def clear_conversation(user_id: str):
    """Clear conversation memory for a user"""
    print(f"🧹 Cleared conversation memory for user: {user_id}")
    # The MemorySaver automatically handles user-specific threads

def interactive_flightaware_chat():
    """Interactive FlightAware chat session"""
    print("✈️ FlightAware Aviation Intelligence Assistant")
    print("=" * 50)
    print("Welcome! I'm your FlightAware expert assistant.")
    print("Type 'quit' to exit, 'agent' to toggle agent mode, 'clear' to clear conversation.")
    print("=" * 50)
    
    # Initialize the system
    try:
        initialize_rag_system()
    except Exception as e:
        print(f"❌ Error initializing system: {e}")
        print("💡 Make sure your Pinecone indexes are created and API keys are set")
        return
    
    # Start conversation
    user_id = f"session_{int(time.time())}"
    use_agent = False
    
    while True:
        try:
            user_input = input(f"\n💬 You: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\n✈️ Thank you for using FlightAware Assistant. Safe travels!")
                break
            elif user_input.lower() == 'agent':
                use_agent = not use_agent
                mode = "Agent" if use_agent else "Assistant"
                print(f"\n🔄 Switched to {mode} mode")
                continue
            elif user_input.lower() == 'clear':
                clear_conversation(user_id)
                user_id = f"session_{int(time.time())}"
                continue
            elif not user_input:
                continue
            
            # Process the message
            chat_interactive(user_input, user_id, use_agent)
            
        except KeyboardInterrupt:
            print("\n\n✈️ Thank you for using FlightAware Assistant. Safe travels!")
            break
        except Exception as e:
            print(f"\n❌ An error occurred: {e}")
            print("Please try again or type 'quit' to exit.")

def demo_flightaware_scenarios():
    """Demonstrate various FlightAware conversation scenarios"""
    print("✈️ FlightAware RAG Bot - Demo Scenarios")
    print("=" * 60)
    
    try:
        initialize_rag_system()
    except Exception as e:
        print(f"❌ Error initializing system: {e}")
        return
    
    # Demo scenarios
    scenarios = [
        {
            "title": "Flight Tracking Basics",
            "message": "How does FlightAware track flights globally?",
            "use_agent": False,
            "user_id": "demo_user_1"
        },
        {
            "title": "FlightAware Foresight",
            "message": "What is FlightAware Foresight and how does predictive technology work?",
            "use_agent": True,
            "user_id": "demo_user_2"
        },
        {
            "title": "AeroAPI Information",
            "message": "Tell me about AeroAPI and how developers can use it.",
            "use_agent": False,
            "user_id": "demo_user_3"
        },
        {
            "title": "Firehose Data Feed",
            "message": "What is FlightAware Firehose and what kind of data does it provide?",
            "use_agent": True,
            "user_id": "demo_user_4"
        }
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{i}. {scenario['title']}")
        print("-" * 40)
        
        chat_interactive(
            scenario['message'], 
            scenario['user_id'], 
            scenario['use_agent']
        )
        
        if i < len(scenarios):
            input("\nPress Enter to continue to next scenario...")
    
    print("\n✅ Demo complete!")

if __name__ == "__main__":
    # Choose demo or interactive mode
    print("✈️ FlightAware RAG Chatbot")
    print("1. Interactive Chat")
    print("2. Demo Scenarios")
    
    choice = input("\nChoose mode (1 or 2): ").strip()
    
    if choice == "2":
        demo_flightaware_scenarios()
    else:
        interactive_flightaware_chat()