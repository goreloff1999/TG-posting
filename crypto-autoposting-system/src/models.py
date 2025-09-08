"""
Database models for crypto autoposting system
"""
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, 
    Float, JSON, ForeignKey, Index, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.dialects.postgresql import UUID
import uuid

from .config import settings

Base = declarative_base()

# Enums
class ContentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ARCHIVED = "archived"

class ContentType(str, Enum):
    NEWS = "news"
    ANALYSIS = "analysis"
    LEAK = "leak"
    TECHNICAL = "technical"
    REGULATORY = "regulatory"

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium" 
    HIGH = "high"

class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Source(Base):
    """Content sources (Telegram channels, Twitter accounts, etc.)"""
    __tablename__ = "sources"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    platform = Column(String(50), nullable=False)  # telegram, twitter, reddit
    username = Column(String(255), nullable=False)
    weight = Column(Float, default=1.0)
    is_active = Column(Boolean, default=True)
    last_checked = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    raw_contents = relationship("RawContent", back_populates="source")
    
    __table_args__ = (
        Index("idx_sources_platform_username", "platform", "username"),
    )


class RawContent(Base):
    """Raw content collected from sources"""
    __tablename__ = "raw_content"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    external_id = Column(String(255))  # Original post ID from platform
    text = Column(Text)
    media_urls = Column(JSON, default=list)  # List of media URLs
    author = Column(String(255))
    published_at = Column(DateTime)
    reactions_count = Column(Integer, default=0)
    views_count = Column(Integer, default=0)
    language = Column(String(10))
    metadata = Column(JSON, default=dict)
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    source = relationship("Source", back_populates="raw_contents")
    processed_content = relationship("ProcessedContent", back_populates="raw_content", uselist=False)
    
    __table_args__ = (
        Index("idx_raw_content_source_external", "source_id", "external_id"),
        Index("idx_raw_content_published_at", "published_at"),
        Index("idx_raw_content_processed", "processed"),
    )


class ProcessedContent(Base):
    """Processed and analyzed content"""
    __tablename__ = "processed_content"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_content_id = Column(UUID(as_uuid=True), ForeignKey("raw_content.id"), nullable=False)
    
    # Analysis results
    summary = Column(Text)
    key_points = Column(JSON, default=list)
    content_type = Column(String(20))  # news, analysis, leak, etc.
    priority = Column(String(10))  # low, medium, high
    risk_level = Column(String(10))  # low, medium, high
    risk_tags = Column(JSON, default=list)  # rumor, hack, regulation
    
    # Translation
    original_language = Column(String(10))
    translated_text = Column(Text)
    translation_quality_score = Column(Float)
    
    # Paraphrasing
    paraphrased_text = Column(Text)
    headline_short = Column(String(100))
    headline_long = Column(String(200))
    author_note = Column(Text)
    tags = Column(JSON, default=list)
    
    # Similarity check
    similarity_score = Column(Float, default=0.0)
    similar_content_ids = Column(JSON, default=list)
    
    # Status
    status = Column(String(20), default=ContentStatus.PENDING.value)
    requires_hitl = Column(Boolean, default=False)
    
    # Metadata
    processing_metadata = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    raw_content = relationship("RawContent", back_populates="processed_content")
    published_posts = relationship("PublishedPost", back_populates="processed_content")
    
    __table_args__ = (
        Index("idx_processed_content_status", "status"),
        Index("idx_processed_content_priority", "priority"),
        Index("idx_processed_content_similarity", "similarity_score"),
        Index("idx_processed_content_requires_hitl", "requires_hitl"),
    )


class GeneratedImage(Base):
    """Generated or selected images for posts"""
    __tablename__ = "generated_images"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    processed_content_id = Column(UUID(as_uuid=True), ForeignKey("processed_content.id"))
    
    image_url = Column(String(500))  # S3/MinIO URL
    image_type = Column(String(50))  # generated, stock, screenshot
    generation_prompt = Column(Text)
    generator = Column(String(100))  # stable_diffusion, midjourney, etc.
    
    # Image metadata
    width = Column(Integer)
    height = Column(Integer)
    format = Column(String(10))  # jpg, png, webp
    size_bytes = Column(Integer)
    
    # Rights and attribution
    license_type = Column(String(100))
    attribution = Column(Text)
    source_url = Column(String(500))
    
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_generated_images_content", "processed_content_id"),
    )


class PublishedPost(Base):
    """Published posts tracking"""
    __tablename__ = "published_posts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    processed_content_id = Column(UUID(as_uuid=True), ForeignKey("processed_content.id"), nullable=False)
    
    # Publishing details
    platform = Column(String(50), nullable=False)  # telegram, twitter, etc.
    external_post_id = Column(String(255))  # Post ID on platform
    channel_id = Column(String(255))
    
    # Content as published
    final_text = Column(Text)
    final_images = Column(JSON, default=list)
    headline_used = Column(String(200))
    tags_used = Column(JSON, default=list)
    
    # Affiliate link tracking
    contains_affiliate = Column(Boolean, default=False)
    affiliate_link_id = Column(String(100))
    
    # Metrics
    views_count = Column(Integer, default=0)
    likes_count = Column(Integer, default=0) 
    shares_count = Column(Integer, default=0)
    comments_count = Column(Integer, default=0)
    click_through_rate = Column(Float, default=0.0)
    
    # Timestamps
    scheduled_at = Column(DateTime)
    published_at = Column(DateTime, default=datetime.utcnow)
    last_metrics_update = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    processed_content = relationship("ProcessedContent", back_populates="published_posts")
    
    __table_args__ = (
        Index("idx_published_posts_platform", "platform"),
        Index("idx_published_posts_published_at", "published_at"),
        Index("idx_published_posts_affiliate", "contains_affiliate"),
    )


class FeedbackLog(Base):
    """User feedback and corrections for learning"""
    __tablename__ = "feedback_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    processed_content_id = Column(UUID(as_uuid=True), ForeignKey("processed_content.id"))
    published_post_id = Column(UUID(as_uuid=True), ForeignKey("published_posts.id"))
    
    feedback_type = Column(String(50))  # style, tone, factcheck, structure
    original_text = Column(Text)
    corrected_text = Column(Text)
    feedback_comment = Column(Text)
    severity = Column(String(10))  # low, medium, high
    
    # Auto-categorization
    feedback_category = Column(String(100))
    keywords = Column(JSON, default=list)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    applied = Column(Boolean, default=False)
    
    __table_args__ = (
        Index("idx_feedback_logs_type", "feedback_type"),
        Index("idx_feedback_logs_severity", "severity"),
    )


class ContentArchive(Base):
    """Archive of all published content for similarity checking"""
    __tablename__ = "content_archive"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    processed_content_id = Column(UUID(as_uuid=True), ForeignKey("processed_content.id"))
    
    title = Column(String(500))
    content_text = Column(Text)
    content_embedding = Column(JSON)  # Vector embedding for similarity
    entities = Column(JSON, default=list)  # Extracted entities
    topics = Column(JSON, default=list)  # Topic tags
    
    published_at = Column(DateTime)
    platform = Column(String(50))
    engagement_score = Column(Float, default=0.0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_content_archive_published_at", "published_at"),
        Index("idx_content_archive_entities", "entities", postgresql_using="gin"),
        Index("idx_content_archive_topics", "topics", postgresql_using="gin"),
    )


class SystemMetrics(Base):
    """System performance and quality metrics"""
    __tablename__ = "system_metrics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Float)
    metric_metadata = Column(JSON, default=dict)
    
    timestamp = Column(DateTime, default=datetime.utcnow)
    period = Column(String(20))  # hourly, daily, weekly
    
    __table_args__ = (
        Index("idx_system_metrics_name_timestamp", "metric_name", "timestamp"),
    )


# Database setup
def create_database_engine():
    """Create database engine"""
    engine = create_engine(
        settings.database_url,
        pool_size=20,
        max_overflow=30,
        pool_pre_ping=True,
        echo=settings.debug
    )
    return engine


def create_tables(engine):
    """Create all tables"""
    Base.metadata.create_all(bind=engine)


def get_session_factory(engine):
    """Get session factory"""
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Initialize
engine = create_database_engine()
SessionLocal = get_session_factory(engine)
