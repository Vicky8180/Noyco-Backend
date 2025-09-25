# api_gateway/database/db.py
import logging
from pymongo import MongoClient
from pymongo.database import Database
from .mongo_helper import create_mongo_client, test_mongo_connection

logger = logging.getLogger(__name__)

class DatabaseConnection:
    _instance = None
    _db = None
    _settings = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseConnection, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._db is None:
            # Import settings here to avoid circular import
            if self._settings is None:
                if __package__ is None or __package__ == '':
                    import sys
                    from os import path
                    sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
                    from api_gateway.config import get_settings
                    self._settings = get_settings()
                else:
                    from ..config import get_settings
                    self._settings = get_settings()
            
            mongo_uri = self._settings.MONGODB_URI
            db_name = self._settings.DATABASE_NAME

            # Enhanced MongoDB connection using helper function
            logger.info("🔄 Initializing MongoDB connection for API Gateway...")
            self.client = create_mongo_client(mongo_uri, max_retries=5, retry_delay=2)
            
            if self.client is None:
                logger.error("❌ Failed to create MongoDB client after multiple attempts")
                raise ConnectionError("Unable to connect to MongoDB")
            
            # Test connection and database access
            if not test_mongo_connection(self.client, db_name):
                logger.error(f"❌ Failed to access database '{db_name}'")
                raise ConnectionError(f"Unable to access database '{db_name}'")
            
            self._db = self.client[db_name]
            logger.info(f"✅ MongoDB connection established successfully for database '{db_name}'")

            # Create indexes
            self._create_indexes()

    def test_connection(self):
        """Test MongoDB connection with retry logic"""
        import time
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                # Test connection
                self.client.admin.command('ping')
                logger.info(f"✅ MongoDB connection successful on attempt {attempt + 1}")
                return True
            except Exception as e:
                logger.warning(f"⚠️ MongoDB connection attempt {attempt + 1} failed: {str(e)[:100]}...")
                if attempt < max_retries - 1:
                    logger.info(f"🔄 Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error("❌ All MongoDB connection attempts failed")
                    raise
        return False

    def get_database(self):
        """Get the database instance"""
        return self._db
        
    def get_client(self):
        """Get the MongoDB client instance"""
        return self.client
        
    def close_connection(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            logger.info("🔒 MongoDB connection closed")

    def _create_indexes(self):
        """Create database indexes for better performance"""
        # Hospitals indexes
        # self._db.hospitals.create_index("email", unique=True)
        # self._db.hospitals.create_index("id", unique=True)

        # Individual user indexes
        self._db.individuals.create_index("email", unique=True)
        self._db.individuals.create_index("id", unique=True)

        # System entity indexes
        self._db.system_entities.create_index("id", unique=True)

        # Assistant indexes
        self._db.assistants.create_index("email", unique=True)
        self._db.assistants.create_index("id", unique=True)
        self._db.assistants.create_index("hospital_id")

        # Users indexes
        self._db.users.create_index("email", unique=True)
        self._db.users.create_index("role_entity_id")
        self._db.users.create_index([("role_entity_id", 1), ("role", 1)])

        # Refresh tokens indexes
        self._db.refresh_tokens.create_index("token", unique=True)
        self._db.refresh_tokens.create_index("user_id")
        self._db.refresh_tokens.create_index("role_entity_id")
        self._db.refresh_tokens.create_index("expires_at", expireAfterSeconds=0)

        # User profiles indexes
        self._db.user_profiles.create_index("user_id", unique=True)
        self._db.user_profiles.create_index("id", unique=True)

        # Conversation transcripts indexes
        self._db.conversation_transcripts.create_index([("conversation_id", 1), ("timestamp", 1)])

        self._db.user_profiles.create_index("id", unique=True)

    @property
    def db(self) -> Database:
        return self._db

def get_database() -> Database:
    """Get database instance"""
    return DatabaseConnection().db
