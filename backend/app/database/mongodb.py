import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DATABASE_RAW = os.getenv("MONGODB_DATABASE")
if not MONGODB_DATABASE_RAW:
    raise RuntimeError("Missing required environment variable: MONGODB_DATABASE")
MONGODB_DATABASE = MONGODB_DATABASE_RAW

client = MongoClient(MONGODB_URI, tz_aware=True)

db = client[MONGODB_DATABASE]


def get_database():
    return db


def check_database_connection():
    client.admin.command("ping")
    return True