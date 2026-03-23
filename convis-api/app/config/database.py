from pymongo import MongoClient
from pymongo.errors import ConfigurationError, ConnectionFailure
from .settings import settings
import logging
import os

logger = logging.getLogger(__name__)

class Database:
    client = None
    db = None

    @classmethod
    def connect(cls):
        """Connect to MongoDB"""
        if cls.client is None:
            try:
                # Force use of Google DNS for DNS resolution
                import dns.resolver
                dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
                dns.resolver.default_resolver.nameservers = ['8.8.8.8', '8.8.4.4']

                # Production-ready configuration for 1000+ concurrent users
                # Optimized for high concurrency with proper timeouts
                cls.client = MongoClient(
                    settings.mongodb_uri,
                    serverSelectionTimeoutMS=10000,  # Reduced from 30s for faster failure
                    connectTimeoutMS=10000,  # Reduced from 20s
                    socketTimeoutMS=30000,  # 30s query timeout (reduced from 45s)
                    retryWrites=True,
                    retryReads=True,
                    maxPoolSize=300,  # Increased from 200 for 1000s of concurrent users
                    minPoolSize=20,  # Increased from 10 to keep more connections warm
                    maxIdleTimeMS=60000,  # Close idle connections after 60s
                    waitQueueTimeoutMS=5000,  # Max wait 5s for available connection (reduced from 10s)
                    maxConnecting=10,  # Max connections being established simultaneously
                    heartbeatFrequencyMS=10000,  # Heartbeat every 10s to detect dead connections
                )
                # Test the connection
                cls.client.admin.command('ping')
                cls.db = cls.client[settings.database_name]
                logger.info("Successfully connected to MongoDB")
            except ConfigurationError as e:
                logger.error(f"MongoDB Configuration Error: {e}")
                logger.error("Please check your MongoDB connection string in .env file")
                logger.error("The MongoDB cluster might not exist or DNS cannot resolve the hostname")
                raise
            except ConnectionFailure as e:
                logger.error(f"Failed to connect to MongoDB: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error connecting to MongoDB: {e}")
                raise
        return cls.db

    @classmethod
    def get_db(cls):
        """Get database instance"""
        if cls.db is None:
            cls.connect()
        return cls.db

    @classmethod
    def close(cls):
        """Close database connection"""
        if cls.client:
            cls.client.close()
            cls.client = None
            cls.db = None
