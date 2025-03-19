# File: database.py
import os
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, BigInteger
from sqlalchemy.orm import declarative_base, sessionmaker

DB_PATH = os.path.expanduser('~/.config/gdrive_sync/files.db')
Base = declarative_base()


# Define models here (or import them)
class File(Base):
    __tablename__ = 'files'
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(10), nullable=False)  # 'file' or 'folder'
    local_path = Column(String, unique=True)
    remote_id = Column(String, unique=True)
    name = Column(String, nullable=False)
    parent_id = Column(Integer, ForeignKey('files.id'))
    checksum = Column(String(64))  # SHA-256
    last_modified_local = Column(DateTime)
    last_modified_remote = Column(DateTime)
    sync_status = Column(String(20), nullable=False)
    file_size = Column(BigInteger)
    local_size = Column(BigInteger)


class SyncHistory(Base):
    __tablename__ = 'sync_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(Integer, ForeignKey('files.id'), nullable=False)
    sync_timestamp = Column(DateTime, server_default='CURRENT_TIMESTAMP')
    action = Column(String(20), nullable=False)  # upload/download/delete
    status = Column(String(10), nullable=False)  # success/failed
    error_message = Column(String)


# Initialize engine and session
engine = create_engine(f'sqlite:///{DB_PATH}')
Session = sessionmaker(bind=engine)


def init_db():
    """Create tables if they don't exist"""
    Base.metadata.create_all(engine)
