from fastapi import APIRouter, HTTPException
from app.models.ai_assistant import DatabaseConnectionTestRequest, DatabaseConnectionTestResponse, DatabaseConfig
from app.config.database import Database
import psycopg2
from psycopg2 import sql
import pymongo
import re
from typing import Optional


def _validate_identifier(name: str) -> str:
    """
    Validate and sanitize SQL identifier (table/column names).
    Prevents SQL injection by only allowing alphanumeric chars and underscores.
    """
    if not name:
        raise ValueError("Identifier cannot be empty")
    # Only allow alphanumeric characters, underscores, and dots (for schema.table)
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_\.]*$', name):
        raise ValueError(f"Invalid identifier: {name}")
    return name

router = APIRouter()

# Get database instance
def get_db():
    return Database.get_db()

@router.post("/{assistant_id}/test-connection")
async def test_database_connection(
    assistant_id: str,
    config: DatabaseConnectionTestRequest
) -> DatabaseConnectionTestResponse:
    """
    Test database connection and return connection status
    """
    try:
        if not config.enabled:
            return DatabaseConnectionTestResponse(
                success=False,
                message="Database integration is not enabled"
            )

        record_count = None

        if config.type == "postgresql":
            record_count = await test_postgresql_connection(config)
        elif config.type == "mysql":
            record_count = await test_mysql_connection(config)
        elif config.type == "mongodb":
            record_count = await test_mongodb_connection(config)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported database type: {config.type}")

        return DatabaseConnectionTestResponse(
            success=True,
            message=f"Successfully connected to {config.type.upper()} database. Found {record_count} records in table '{config.table_name}'.",
            record_count=record_count
        )

    except Exception as e:
        return DatabaseConnectionTestResponse(
            success=False,
            message=f"Connection failed: {str(e)}"
        )

async def test_postgresql_connection(config: DatabaseConnectionTestRequest) -> int:
    """Test PostgreSQL connection and return record count"""
    try:
        conn = psycopg2.connect(
            host=config.host,
            port=int(config.port),
            database=config.database,
            user=config.username,
            password=config.password,
            connect_timeout=10
        )

        cursor = conn.cursor()
        # Validate table name to prevent SQL injection
        table_name = _validate_identifier(config.table_name)
        cursor.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table_name)))
        count = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return count
    except Exception as e:
        raise Exception(f"PostgreSQL connection error: {str(e)}")

async def test_mysql_connection(config: DatabaseConnectionTestRequest) -> int:
    """Test MySQL connection and return record count"""
    try:
        import mysql.connector

        conn = mysql.connector.connect(
            host=config.host,
            port=int(config.port),
            database=config.database,
            user=config.username,
            password=config.password,
            connection_timeout=10
        )

        cursor = conn.cursor()
        # Validate table name to prevent SQL injection
        table_name = _validate_identifier(config.table_name)
        # MySQL uses backticks for identifier quoting
        cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
        count = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return count
    except Exception as e:
        raise Exception(f"MySQL connection error: {str(e)}")

async def test_mongodb_connection(config: DatabaseConnectionTestRequest) -> int:
    """Test MongoDB connection and return record count"""
    try:
        client = pymongo.MongoClient(
            host=config.host,
            port=int(config.port),
            username=config.username,
            password=config.password,
            serverSelectionTimeoutMS=10000
        )

        db_conn = client[config.database]
        collection = db_conn[config.table_name]
        count = collection.count_documents({})

        client.close()

        return count
    except Exception as e:
        raise Exception(f"MongoDB connection error: {str(e)}")

@router.post("/{assistant_id}/save-config")
async def save_database_config(
    assistant_id: str,
    config: DatabaseConfig
):
    """
    Save database configuration to assistant
    """
    try:
        db = get_db()
        result = db.assistants.update_one(
            {"_id": assistant_id},
            {
                "$set": {
                    "database_config": config.dict()
                }
            }
        )

        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Assistant not found")

        return {"message": "Database configuration saved successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save database configuration: {str(e)}")

@router.get("/{assistant_id}/config")
async def get_database_config(assistant_id: str) -> Optional[DatabaseConfig]:
    """
    Get database configuration for an assistant
    """
    try:
        db = get_db()
        assistant = db.assistants.find_one({"_id": assistant_id})

        if not assistant:
            raise HTTPException(status_code=404, detail="Assistant not found")

        if "database_config" in assistant and assistant["database_config"]:
            return DatabaseConfig(**assistant["database_config"])

        return None

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve database configuration: {str(e)}")

async def query_database(config: DatabaseConfig, query_text: str) -> Optional[dict]:
    """
    Query the configured database based on user input
    Used by the RAG system to fetch relevant user data
    """
    try:
        if not config.enabled:
            return None

        if config.type == "postgresql":
            return await query_postgresql(config, query_text)
        elif config.type == "mysql":
            return await query_mysql(config, query_text)
        elif config.type == "mongodb":
            return await query_mongodb(config, query_text)

        return None

    except Exception as e:
        print(f"Database query error: {str(e)}")
        return None

async def query_postgresql(config: DatabaseConfig, query_text: str) -> Optional[dict]:
    """Query PostgreSQL database for relevant records"""
    try:
        conn = psycopg2.connect(
            host=config.host,
            port=int(config.port),
            database=config.database,
            user=config.username,
            password=config.password,
            connect_timeout=10
        )

        cursor = conn.cursor()

        # Validate identifiers to prevent SQL injection
        table_name = _validate_identifier(config.table_name)
        validated_columns = [_validate_identifier(col) for col in config.search_columns]

        # Build search query across specified columns using psycopg2.sql for safe queries
        search_conditions = []
        for column in validated_columns:
            search_conditions.append(
                sql.SQL("{}::text ILIKE %s").format(sql.Identifier(column))
            )

        where_clause = sql.SQL(" OR ").join(search_conditions)
        query = sql.SQL("SELECT * FROM {} WHERE {} LIMIT 10").format(
            sql.Identifier(table_name),
            where_clause
        )

        search_term = f"%{query_text}%"
        params = tuple([search_term] * len(config.search_columns))

        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        results = []
        for row in rows:
            results.append(dict(zip(columns, row)))

        cursor.close()
        conn.close()

        return {
            "source": "database",
            "database_type": "postgresql",
            "table": config.table_name,
            "records": results,
            "count": len(results)
        }
    except Exception as e:
        print(f"PostgreSQL query error: {str(e)}")
        return None

async def query_mysql(config: DatabaseConfig, query_text: str) -> Optional[dict]:
    """Query MySQL database for relevant records"""
    try:
        import mysql.connector

        conn = mysql.connector.connect(
            host=config.host,
            port=int(config.port),
            database=config.database,
            user=config.username,
            password=config.password,
            connection_timeout=10
        )

        cursor = conn.cursor(dictionary=True)

        # Validate identifiers to prevent SQL injection
        table_name = _validate_identifier(config.table_name)
        validated_columns = [_validate_identifier(col) for col in config.search_columns]

        # Build search query across specified columns with backtick quoting
        search_conditions = []
        for column in validated_columns:
            search_conditions.append(f"`{column}` LIKE %s")

        where_clause = " OR ".join(search_conditions)
        # Table name and columns are validated by _validate_identifier() above
        query = f"SELECT * FROM `{table_name}` WHERE {where_clause} LIMIT 10"  # nosec B608

        search_term = f"%{query_text}%"
        params = tuple([search_term] * len(config.search_columns))

        cursor.execute(query, params)
        results = cursor.fetchall()

        cursor.close()
        conn.close()

        return {
            "source": "database",
            "database_type": "mysql",
            "table": config.table_name,
            "records": results,
            "count": len(results)
        }
    except Exception as e:
        print(f"MySQL query error: {str(e)}")
        return None

async def query_mongodb(config: DatabaseConfig, query_text: str) -> Optional[dict]:
    """Query MongoDB database for relevant documents"""
    try:
        client = pymongo.MongoClient(
            host=config.host,
            port=int(config.port),
            username=config.username,
            password=config.password,
            serverSelectionTimeoutMS=10000
        )

        db_conn = client[config.database]
        collection = db_conn[config.table_name]

        # Build search query across specified fields
        search_conditions = []
        for field in config.search_columns:
            search_conditions.append({field: {"$regex": query_text, "$options": "i"}})

        query = {"$or": search_conditions} if search_conditions else {}

        results = list(collection.find(query).limit(10))

        # Convert ObjectId to string for JSON serialization
        for result in results:
            if "_id" in result:
                result["_id"] = str(result["_id"])

        client.close()

        return {
            "source": "database",
            "database_type": "mongodb",
            "collection": config.table_name,
            "documents": results,
            "count": len(results)
        }
    except Exception as e:
        print(f"MongoDB query error: {str(e)}")
        return None
