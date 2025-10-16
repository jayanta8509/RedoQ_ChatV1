"""
Pinecone Vector Database Storage Module
Handles loading and storing JSON data into Pinecone vector database

Data Sources:
- JSON files (scraped data or other structured data)
"""

import os
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
import pandas as pd
import time
import logging

# LangChain imports for document processing
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_core.documents import Document

# Pinecone imports
from pinecone import Pinecone, ServerlessSpec

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class JSONPineconeManager:
    """
    Manages the creation and storage of Pinecone vector database
    from JSON files
    """
    
    def __init__(self, 
                 json_file: str,
                 index_name: str,
                 embedding_model: str = "text-embedding-3-large"):
        """
        Initialize the JSON Pinecone manager
        
        Args:
            json_file: Path to JSON file containing data
            index_name: Name of the Pinecone index
            embedding_model: OpenAI embedding model to use
        """
        self.json_file = Path(json_file)
        self.index_name = index_name
        self.embedding_model = embedding_model
        
        # Initialize Pinecone
        self.setup_pinecone()
        
        # Initialize embeddings
        self.embeddings = OpenAIEmbeddings(model=self.embedding_model)
        
        # Initialize text splitter for long content
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )
        
        logger.info(f"JSONPineconeManager initialized")
        logger.info(f"JSON file: {self.json_file}")
        logger.info(f"Pinecone index: {self.index_name}")
    
    def setup_pinecone(self):
        """Setup Pinecone connection and index"""
        # Get API key from environment
        api_key = os.getenv("PINECONE_API_KEY")
        if not api_key:
            raise ValueError("PINECONE_API_KEY not found in environment variables")
        
        # Initialize Pinecone
        self.pc = Pinecone(api_key=api_key)
        
        # Check if index exists, create if not
        existing_indexes = [index.name for index in self.pc.list_indexes()]
        
        if self.index_name not in existing_indexes:
            logger.info(f"Creating new Pinecone index: {self.index_name}")
            self.pc.create_index(
                name=self.index_name,
                dimension=3072,  # dimension for text-embedding-3-large
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
            # Wait for index to be ready
            time.sleep(10)
        
        # Connect to index
        self.index = self.pc.Index(self.index_name)
        logger.info(f"Connected to Pinecone index: {self.index_name}")
    
    def load_json_data(self) -> List[Dict]:
        """
        Load JSON data from file
        
        Returns:
            List of JSON objects
        """
        logger.info(f"Loading JSON data from: {self.json_file}")
        
        if not self.json_file.exists():
            raise FileNotFoundError(f"JSON file not found: {self.json_file}")
        
        with open(self.json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        logger.info(f"Loaded {len(data)} records from JSON file")
        return data
    
    def json_to_documents(self) -> List[Document]:
        """
        Convert JSON data to LangChain Document objects
        
        Returns:
            List of Document objects
        """
        logger.info("Converting JSON data to documents...")
        json_data = self.load_json_data()
        documents = []
        
        for idx, item in enumerate(json_data):
            # Extract fields from JSON
            url = item.get('url', 'Unknown')
            title = item.get('title', 'Unknown')
            content = item.get('content', '')
            metadata_dict = item.get('metadata', {})
            
            # Create content text
            full_content = f"Title: {title}\n\nContent: {content}"
            
            # Create metadata for the document
            doc_metadata = {
                'source': self.json_file.name,
                'file_type': 'json',
                'url': url,
                'title': title,
                'record_index': idx,
                'index_name': self.index_name
            }
            
            # Add additional metadata fields
            if metadata_dict:
                doc_metadata['description'] = metadata_dict.get('description', '')
                doc_metadata['og_title'] = metadata_dict.get('og:title', '')
            
            # Create document
            doc = Document(
                page_content=full_content,
                metadata=doc_metadata
            )
            
            # Split long documents into chunks
            if len(full_content) > 1000:
                chunks = self.text_splitter.split_documents([doc])
                documents.extend(chunks)
            else:
                documents.append(doc)
        
        logger.info(f"Created {len(documents)} document chunks from {len(json_data)} JSON records")
        return documents
    
    def analyze_json_data(self):
        """
        Analyze JSON data structure and content
        """
        logger.info("Analyzing JSON data...")
        
        json_data = self.load_json_data()
        
        logger.info(f"Total records: {len(json_data)}")
        
        if json_data:
            # Show sample record
            sample = json_data[0]
            logger.info(f"Sample record keys: {list(sample.keys())}")
            logger.info(f"Sample URL: {sample.get('url', 'N/A')}")
            logger.info(f"Sample title: {sample.get('title', 'N/A')[:100]}...")
            logger.info(f"Content length: {len(sample.get('content', ''))} characters")
            logger.info(f"Metadata keys: {list(sample.get('metadata', {}).keys())}")
            
            # Calculate statistics
            total_content_length = sum(len(item.get('content', '')) for item in json_data)
            avg_content_length = total_content_length / len(json_data)
            
            logger.info(f"Average content length: {int(avg_content_length)} characters")
            logger.info(f"Total content: {total_content_length} characters")
    
    def create_vector_store(self) -> PineconeVectorStore:
        """
        Create Pinecone vector store from JSON data
        
        Returns:
            PineconeVectorStore object
        """
        logger.info("Creating JSON Pinecone vector store...")
        
        # Convert JSON to documents
        documents = self.json_to_documents()
        
        if not documents:
            raise ValueError("No documents found to create vector store")
        
        logger.info(f"Total documents to vectorize: {len(documents)}")
        
        # Create Pinecone vector store
        logger.info("Creating embeddings and uploading to Pinecone...")
        vector_store = PineconeVectorStore(
            embedding=self.embeddings,
            index=self.index
        )
        
        # Add documents in batches to avoid timeout
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i+batch_size]
            logger.info(f"Uploading batch {i//batch_size + 1}/{(len(documents)-1)//batch_size + 1}")
            vector_store.add_documents(batch)
            time.sleep(1)
        
        logger.info("JSON Pinecone vector store created successfully!")
        return vector_store
    
    def load_vector_store(self) -> PineconeVectorStore:
        """
        Load existing Pinecone vector store
        
        Returns:
            PineconeVectorStore object
        """
        logger.info(f"Loading JSON Pinecone vector store from index: {self.index_name}")
        
        vector_store = PineconeVectorStore(
            embedding=self.embeddings,
            index=self.index
        )
        
        # Check if index has data
        stats = self.index.describe_index_stats()
        total_vectors = stats.get('total_vector_count', 0)
        
        logger.info(f"Index stats: {total_vectors} vectors in index")
        logger.info("JSON Pinecone vector store loaded successfully!")
        
        return vector_store
    
    def create_and_upload_vector_store(self) -> PineconeVectorStore:
        """
        Complete workflow: create and upload JSON vector store to Pinecone
        
        Returns:
            PineconeVectorStore object
        """
        logger.info("Starting JSON Pinecone vector store creation workflow...")
        
        # Create and upload vector store
        vector_store = self.create_vector_store()
        
        # Save metadata to local file for reference
        self.save_metadata()
        
        logger.info("JSON Pinecone vector store creation and upload complete!")
        return vector_store
    
    def save_metadata(self):
        """Save metadata about the uploaded data"""
        json_data = self.load_json_data()
        
        metadata = {
            "data_type": "json",
            "embedding_model": self.embedding_model,
            "index_name": self.index_name,
            "json_file": str(self.json_file),
            "created_date": pd.Timestamp.now().isoformat(),
            "total_records": len(json_data),
            "pinecone_index_stats": self.index.describe_index_stats()
        }
        
        metadata_file = f"json_pinecone_metadata_{self.index_name}.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2, default=str)
        
        logger.info(f"Metadata saved to: {metadata_file}")
    
    def search_vectors(self, query: str, k: int = 5, filter_dict: Optional[Dict] = None):
        """
        Search the Pinecone vector store
        
        Args:
            query: Search query
            k: Number of results to return
            filter_dict: Optional metadata filter
        
        Returns:
            List of search results
        """
        vector_store = self.load_vector_store()
        
        logger.info(f"Searching JSON vectors for: '{query}'")
        
        if filter_dict:
            results = vector_store.similarity_search(query, k=k, filter=filter_dict)
            logger.info(f"Applied filter: {filter_dict}")
        else:
            results = vector_store.similarity_search(query, k=k)
        
        logger.info(f"Found {len(results)} results")
        
        return results
    
    def delete_index(self):
        """Delete the Pinecone index (use with caution!)"""
        logger.warning(f"Deleting Pinecone index: {self.index_name}")
        self.pc.delete_index(self.index_name)
        logger.info("Index deleted successfully!")


def upload_json_to_pinecone(json_file_path: str, index_name: str, embedding_model: str = "text-embedding-3-large") -> PineconeVectorStore:
    """
    Main function to upload JSON data to Pinecone vector store
    
    Args:
        json_file_path: Path to JSON file containing data
        index_name: Name of the Pinecone index
        embedding_model: OpenAI embedding model to use
    
    Returns:
        PineconeVectorStore object
    """
    logger.info("Starting JSON to Pinecone upload process...")
    
    # Initialize JSON Pinecone manager
    manager = JSONPineconeManager(
        json_file=json_file_path,
        index_name=index_name,
        embedding_model=embedding_model
    )
    
    # Analyze JSON data first
    manager.analyze_json_data()
    
    # Create and upload vector store
    vector_store = manager.create_and_upload_vector_store()
    
    logger.info("JSON upload to Pinecone complete!")
    
    return vector_store


if __name__ == "__main__":
    # Example usage
    vector_store = upload_json_to_pinecone(
        json_file_path="scraping/flightaware_data.json",
        index_name="flightaware-data"
    )
