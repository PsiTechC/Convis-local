"""
Pytest configuration and fixtures for integration tests
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock, patch
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class MockMongoCollection:
    """Mock MongoDB collection with in-memory storage"""
    def __init__(self):
        self.storage = {}
        self.counter = 0

    def insert_one(self, data):
        from bson import ObjectId
        doc_id = ObjectId()
        self.storage[str(doc_id)] = {**data, "_id": doc_id}
        result = MagicMock()
        result.inserted_id = doc_id
        return result

    def find_one(self, query):
        if "_id" in query:
            doc_id = str(query["_id"])
            return self.storage.get(doc_id)
        # For other queries, search through storage
        for doc in self.storage.values():
            match = True
            for key, value in query.items():
                if doc.get(key) != value:
                    match = False
                    break
            if match:
                return doc
        return None

    def find(self, query=None):
        if query is None:
            return MockCursor(list(self.storage.values()))
        results = []
        for doc in self.storage.values():
            match = True
            for key, value in query.items():
                if doc.get(key) != value:
                    match = False
                    break
            if match:
                results.append(doc)
        return MockCursor(results)

    def update_one(self, query, update):
        doc = self.find_one(query)
        if doc and "$set" in update:
            doc.update(update["$set"])
        result = MagicMock()
        result.modified_count = 1 if doc else 0
        return result

    def delete_one(self, query):
        doc = self.find_one(query)
        if doc and "_id" in doc:
            del self.storage[str(doc["_id"])]
        result = MagicMock()
        result.deleted_count = 1 if doc else 0
        return result


class MockCursor:
    """Mock MongoDB cursor"""
    def __init__(self, data):
        self.data = data

    def __iter__(self):
        return iter(self.data)

    def sort(self, *args, **kwargs):
        return self

    def skip(self, n):
        self.data = self.data[n:]
        return self

    def limit(self, n):
        self.data = self.data[:n]
        return self

    def count(self):
        return len(self.data)


class MockDatabase:
    """Mock MongoDB database"""
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = MockMongoCollection()
        return self.collections[name]


@pytest.fixture
def client():
    """
    Create a FastAPI TestClient for integration tests with mocked database
    """
    mock_db = MockDatabase()

    with patch('app.config.database.Database.get_db', return_value=mock_db):
        from app.main import app
        with TestClient(app) as test_client:
            yield test_client


@pytest.fixture
def mock_mongo_db():
    """
    Mock MongoDB for tests that don't need the full API
    """
    return MockDatabase()


@pytest.fixture
def mock_twilio_ws():
    """
    Mock Twilio WebSocket for tests
    """
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock()
    return mock_ws


# Register custom marks
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as unit test"
    )
