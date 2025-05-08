# from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey
# from sqlalchemy.orm import relationship, sessionmaker
# from sqlalchemy.ext.declarative import declarative_base
# import os
# from datetime import datetime

# DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@db:5432/wfh_monitoring")

# engine = create_engine(DATABASE_URL)
# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Base = declarative_base()

# class User(Base):
#     __tablename__ = "users"
#     id = Column(Integer, primary_key=True, index=True)
#     username = Column(String, unique=True, nullable=False)
#     email = Column(String, unique=True, nullable=True)
#     is_active = Column(Boolean, default=True)
#     created_at = Column(DateTime, default=datetime.utcnow)

#     # Relationship to daily summaries
#     daily_summaries = relationship("DailySummary", back_populates="user")

# class Session(Base):
#     __tablename__ = "sessions"
#     id = Column(Integer, primary_key=True, index=True)
#     user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
#     channel = Column(String, nullable=True)
#     screen_shared = Column(Boolean, default=False)
#     screen_share_time = Column(Integer, default=0)
#     event = Column(String, nullable=True)
#     timestamp = Column(DateTime)

#     # Relationship to user
#     user = relationship("User")

# class Activity(Base):
#     __tablename__ = "activities"
#     id = Column(Integer, primary_key=True, index=True)
#     user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
#     active_apps = Column(String, nullable=True)
#     active_app = Column(String, nullable=True)
#     idle_time = Column(String, nullable=True)
#     timestamp = Column(DateTime)

#     # Relationship to user
#     user = relationship("User")

# class DailySummary(Base):
#     __tablename__ = "daily_summaries"
#     id = Column(Integer, primary_key=True, index=True)
#     user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
#     date = Column(DateTime, default=datetime.utcnow)
#     total_screen_share_time = Column(Integer, default=0)
#     active_apps = Column(String, nullable=True)
#     active_app = Column(String, nullable=True)

#     # Relationship to user
#     user = relationship("User", back_populates="daily_summaries")

# Base.metadata.create_all(bind=engine)