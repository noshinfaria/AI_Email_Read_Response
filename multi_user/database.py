# database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from multi_user.models import Base

DATABASE_URL = "sqlite:///./test.db"  # or your Postgres URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)
