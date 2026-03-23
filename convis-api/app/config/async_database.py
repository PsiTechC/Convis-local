"""
Async Database Configuration using Motor (Async MongoDB Driver)
Provides non-blocking database operations for improved latency
"""
from motor.motor_asyncio import AsyncIOMotorClient
from .settings import settings
import logging
import asyncio

logger = logging.getLogger(__name__)


class AsyncDatabase:
    """Async MongoDB connection manager using Motor"""

    _client: AsyncIOMotorClient = None
    _db = None
    _lock = asyncio.Lock()

    @classmethod
    async def connect(cls):
        """Connect to MongoDB asynchronously"""
        async with cls._lock:
            if cls._client is None:
                try:
                    # Production-ready configuration matching sync database settings
                    cls._client = AsyncIOMotorClient(
                        settings.mongodb_uri,
                        serverSelectionTimeoutMS=10000,
                        connectTimeoutMS=10000,
                        socketTimeoutMS=30000,
                        retryWrites=True,
                        retryReads=True,
                        maxPoolSize=300,
                        minPoolSize=20,
                        maxIdleTimeMS=60000,
                        waitQueueTimeoutMS=5000,
                    )

                    # Test the connection
                    await cls._client.admin.command('ping')
                    cls._db = cls._client[settings.database_name]
                    logger.info("Successfully connected to MongoDB (async)")

                except Exception as e:
                    logger.error(f"Failed to connect to MongoDB (async): {e}")
                    raise

        return cls._db

    @classmethod
    async def get_db(cls):
        """Get async database instance"""
        if cls._db is None:
            await cls.connect()
        return cls._db

    @classmethod
    async def close(cls):
        """Close async database connection"""
        if cls._client:
            cls._client.close()
            cls._client = None
            cls._db = None
            logger.info("Async MongoDB connection closed")

    @classmethod
    def get_client(cls) -> AsyncIOMotorClient:
        """Get the Motor client instance"""
        return cls._client


# Helper function for getting collections asynchronously
async def get_async_collection(collection_name: str):
    """
    Get an async collection by name.

    Usage:
        collection = await get_async_collection("users")
        user = await collection.find_one({"email": "test@example.com"})
    """
    db = await AsyncDatabase.get_db()
    return db[collection_name]
