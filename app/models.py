from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
import datetime
from .database import Base

class Domain(Base):
    __tablename__ = "domains"
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, index=True)
    status = Column(String, default="Pending") # Pending, Crawling, Completed, Failed
    added_at = Column(DateTime, default=datetime.datetime.utcnow)
    urls = relationship("URLItem", back_populates="domain")

class URLItem(Base):
    __tablename__ = "urls"
    id = Column(Integer, primary_key=True, index=True)
    domain_id = Column(Integer, ForeignKey("domains.id"))
    original_url = Column(String)
    normalized_url = Column(String, unique=True, index=True)
    discovery_source = Column(String) # e.g. "HTML link", "Sitemap"
    discovery_timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Queue / Submission Status
    status = Column(String, default="Queued") # Queued, Processing, Submitted, Failed, Skipped
    
    domain = relationship("Domain", back_populates="urls")
    submissions = relationship("ArchiveSubmission", back_populates="url_item")

class ArchiveSubmission(Base):
    __tablename__ = "archive_submissions"
    id = Column(Integer, primary_key=True, index=True)
    url_id = Column(Integer, ForeignKey("urls.id"))
    service = Column(String) # "Wayback Machine", "Archive.today"
    submission_timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String) # "Success", "Failed", "Pending"
    archive_url = Column(String, nullable=True)
    archive_identifier = Column(String, nullable=True)
    http_status = Column(Integer, nullable=True)
    error_message = Column(String, nullable=True)
    last_attempted = Column(DateTime, default=datetime.datetime.utcnow)
    
    url_item = relationship("URLItem", back_populates="submissions")
