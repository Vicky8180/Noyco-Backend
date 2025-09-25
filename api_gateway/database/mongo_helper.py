# api_gateway/database/mongo_helper.py
"""
MongoDB connection helper with enhanced SSL and retry logic for cloud deployment
"""
import logging
import time
from typing import Optional
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, OperationFailure

logger = logging.getLogger(__name__)

def create_mongo_client(mongo_uri: str, max_retries: int = 3, retry_delay: int = 2) -> Optional[MongoClient]:
    """
    Create MongoDB client with enhanced SSL configuration and retry logic
    
    Args:
        mongo_uri: MongoDB connection URI
        max_retries: Maximum number of connection attempts
        retry_delay: Initial delay between retries (exponential backoff)
    
    Returns:
        MongoClient instance or None if connection fails
    """
    
    # Enhanced connection parameters for cloud deployment
    connection_params = {
        'serverSelectionTimeoutMS': 30000,  # 30 seconds
        'connectTimeoutMS': 30000,          # 30 seconds
        'socketTimeoutMS': 30000,           # 30 seconds
        'maxPoolSize': 10,                  # Connection pool size
        'retryWrites': True,                # Retry writes on failure
        'ssl': True,                        # Enable SSL
        'tlsAllowInvalidCertificates': False, # Validate certificates
        'tlsAllowInvalidHostnames': False,   # Validate hostnames
        'directConnection': False,          # Use load balancer
        'appName': 'Noyco-Healthcare-API'   # Application identifier
    }
    
    for attempt in range(max_retries):
        try:
            logger.info(f"🔄 MongoDB connection attempt {attempt + 1}/{max_retries}")
            
            # Create client with enhanced parameters
            client = MongoClient(mongo_uri, **connection_params)
            
            # Test connection
            client.admin.command('ping')
            
            logger.info(f"✅ MongoDB connection successful on attempt {attempt + 1}")
            return client
            
        except ServerSelectionTimeoutError as e:
            logger.warning(f"⚠️ MongoDB server selection timeout (attempt {attempt + 1}): {str(e)[:200]}...")
            if "SSL handshake failed" in str(e):
                logger.error("💡 SSL handshake issue detected. Trying with relaxed SSL settings...")
                # Try with more lenient SSL settings
                relaxed_params = connection_params.copy()
                relaxed_params.update({
                    'tlsInsecure': True,  # Allow insecure connections as fallback
                    'tlsAllowInvalidCertificates': True,
                    'tlsAllowInvalidHostnames': True,
                })
                try:
                    client = MongoClient(mongo_uri, **relaxed_params)
                    client.admin.command('ping')
                    logger.warning("⚠️ MongoDB connected with relaxed SSL settings")
                    return client
                except Exception as relaxed_e:
                    logger.error(f"❌ Relaxed SSL connection also failed: {str(relaxed_e)[:200]}...")
                    
        except OperationFailure as e:
            logger.error(f"❌ MongoDB authentication/operation failed (attempt {attempt + 1}): {str(e)[:200]}...")
            
        except Exception as e:
            logger.error(f"❌ MongoDB connection failed (attempt {attempt + 1}): {str(e)[:200]}...")
            
        # Retry logic with exponential backoff
        if attempt < max_retries - 1:
            wait_time = retry_delay * (2 ** attempt)
            logger.info(f"🔄 Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
        else:
            logger.error("❌ All MongoDB connection attempts failed")
            
    return None

def test_mongo_connection(client: MongoClient, db_name: str) -> bool:
    """
    Test MongoDB connection and database access
    
    Args:
        client: MongoDB client instance
        db_name: Database name to test
        
    Returns:
        True if connection and database access successful, False otherwise
    """
    try:
        # Test server connection
        client.admin.command('ping')
        
        # Test database access
        db = client[db_name]
        db.list_collection_names()
        
        logger.info(f"✅ MongoDB connection and database '{db_name}' access verified")
        return True
        
    except Exception as e:
        logger.error(f"❌ MongoDB connection test failed: {str(e)[:200]}...")
        return False

def get_mongo_connection_info(client: MongoClient) -> dict:
    """
    Get MongoDB connection information for debugging
    
    Args:
        client: MongoDB client instance
        
    Returns:
        Dictionary with connection information
    """
    try:
        server_info = client.server_info()
        topology = client.topology_description
        
        return {
            "server_version": server_info.get("version", "unknown"),
            "topology_type": str(topology.topology_type),
            "server_count": len(topology.server_descriptions()),
            "servers": [
                {
                    "address": f"{server.address[0]}:{server.address[1]}",
                    "type": str(server.server_type),
                    "round_trip_time": server.round_trip_time
                }
                for server in topology.server_descriptions()
            ]
        }
        
    except Exception as e:
        return {"error": str(e)}