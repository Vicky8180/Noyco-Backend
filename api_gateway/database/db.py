# api_gateway/database/db.py
from pymongo import MongoClient
from pymongo.database import Database

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

            self.client = MongoClient(mongo_uri)
            self._db = self.client[db_name]

            # Create indexes
            self._create_indexes()

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
