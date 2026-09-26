import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE")

client = MongoClient(MONGODB_URI, tz_aware=True)

db = client[MONGODB_DATABASE]


def get_database():
    return db


def check_database_connection():
    client.admin.command("ping")
    return True