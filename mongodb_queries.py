from pymongo import MongoClient
from pymongo.errors import PyMongoError
from datetime import datetime
from typing import Any, List, Dict, Optional
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def connect_to_mongo() -> tuple[MongoClient, Any]:
    """
    Connect to MongoDB.
    :return: Tuple containing MongoDB client and database object.
    """
    try:
        # Load MongoDB settings from .env file
        host = os.getenv("MONGO_HOST")
        port = int(os.getenv("MONGO_PORT"))
        username = os.getenv("MONGO_USERNAME")
        password = os.getenv("MONGO_PASSWORD")
        database_name = os.getenv("MONGO_DB")

        # Establish MongoDB connection
        client = MongoClient(host=host, port=port, username=username, password=password)
        db = client[database_name]
        return client, db
    except PyMongoError as e:
        print(f"Error connecting to MongoDB: {e}")
        raise


def fetch_questions_mongo(db: Any, question_ids: List[int]) -> List[Dict[str, Any]]:
    """
    Fetches questions from MongoDB based on a list of question IDs.

    :param db: MongoDB database object.
    :param question_ids: List of question IDs to fetch.
    :return: List of question documents.
    """
    try:
        questions = list(db.questions.find({"question_id": {"$in": question_ids}}))
        return questions
    except PyMongoError as e:
        print(f"Error fetching questions from MongoDB: {e}")
        raise


def log_action_mongo(db: Any, action: str, username: str, description: str, email: Optional[str] = None) -> None:
    """
    Logs an action in the MongoDB 'action_history' collection.

    :param db: MongoDB database object.
    :param action: The action performed (e.g., create_user, start_game, etc.).
    :param username: The username involved in the action.
    :param description: A description of the action performed.
    :param email: The email of the user (optional).
    """
    if not email:  # If email is not provided, retrieve it from the MongoDB log
        email = fetch_email_from_created_record(db, username)

    try:
        action_record = {
            "action": action,
            "username": username,
            "description": description,
            "email": email,
            "timestamp": datetime.now()
        }
        db.action_history.insert_one(action_record)
    except PyMongoError as e:
        print(f"Error logging action to MongoDB: {e}")
        raise


def fetch_email_from_created_record(db, username) -> str | None:
    create_record = db.action_history.find_one(
        {"username": username, "action": "User Register"},
        {"email": 1}  # Only retrieve the email field
    )
    return create_record.get("email") if create_record else None


def fetch_action_history(db: Any) -> List[Dict[str, Any]]:
    """
    Fetches all logged actions from MongoDB.

    :param db: MongoDB database object.
    :return: List of action documents.
    """
    try:
        actions = list(db.action_history.find().sort("timestamp", 1))
        return actions
    except PyMongoError as e:
        print(f"Error fetching action history from MongoDB: {e}")
        raise


def close_mongo_connection(client: MongoClient) -> None:
    """
    Close the MongoDB connection.

    :param client: MongoClient object.
    """
    try:
        client.close()
    except PyMongoError as e:
        print(f"Error closing MongoDB connection: {e}")
        raise
