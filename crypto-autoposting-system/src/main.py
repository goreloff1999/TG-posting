"""
Main application entry point
"""
import logging
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from .config import settings
from .models import create_tables, engine, SessionLocal
from .ingestion.telegram_ingestion import TelegramIngestion
from .ingestion.twitter_ingestion import TwitterIngestion
from .processing.content_processor import ContentProcessor
from .publishing.publisher import PublishingService
from .utils.redis_client import RedisClient

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global services
telegram_ingestion = None
twitter_ingestion = None
content_processor = None
publishing_service = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting Crypto Autoposting System")
    
    # Create database tables
    create_tables(engine)
    logger.info("Database tables created/verified")
    
    # Initialize global services
    global telegram_ingestion, twitter_ingestion, content_processor, publishing_service
    
    telegram_ingestion = TelegramIngestion()
    twitter_ingestion = TwitterIngestion()
    content_processor = ContentProcessor()
    publishing_service = PublishingService()
    
    # Start background services
    background_tasks = []
    
    try:
        # Start ingestion services
        background_tasks.append(asyncio.create_task(telegram_ingestion.start()))
        background_tasks.append(asyncio.create_task(twitter_ingestion.start()))
        
        # Start processing services
        background_tasks.append(asyncio.create_task(content_processor.process_content_queue()))
        
        # Start publishing services
        background_tasks.append(asyncio.create_task(publishing_service.process_publishing_queue()))
        
        logger.info("Background services started")
        
        yield
        
    finally:
        # Shutdown
        logger.info("Shutting down services...")
        
        # Cancel background tasks
        for task in background_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Close services
        if telegram_ingestion:
            await telegram_ingestion.stop()
        if twitter_ingestion:
            await twitter_ingestion.stop()
        if content_processor:
            content_processor.close()
        if publishing_service:
            publishing_service.close()
        
        logger.info("Services shut down complete")


# Create FastAPI app
app = FastAPI(
    title="Crypto Autoposting System",
    description="Automated crypto news collection, processing, and publishing system",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }


# API Endpoints
@app.get("/api/stats")
async def get_system_stats():
    """Get system statistics"""
    try:
        session = SessionLocal()
        
        # Get content stats
        from .models import RawContent, ProcessedContent, PublishedPost
        
        stats = {
            "content": {
                "raw_content_count": session.query(RawContent).count(),
                "processed_content_count": session.query(ProcessedContent).count(),
                "published_posts_count": session.query(PublishedPost).count(),
            },
            "processing": {
                "pending_processing": session.query(ProcessedContent).filter(
                    ProcessedContent.status == "pending"
                ).count(),
                "ready_for_publishing": session.query(ProcessedContent).filter(
                    ProcessedContent.status == "ready"
                ).count(),
                "requires_hitl": session.query(ProcessedContent).filter(
                    ProcessedContent.requires_hitl == True
                ).count()
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        session.close()
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get statistics")


@app.get("/api/content/{content_id}")
async def get_content(content_id: str):
    """Get specific content by ID"""
    try:
        session = SessionLocal()
        
        from .models import ProcessedContent
        
        content = session.query(ProcessedContent).filter(
            ProcessedContent.id == content_id
        ).first()
        
        if not content:
            session.close()
            raise HTTPException(status_code=404, detail="Content not found")
        
        result = {
            "id": str(content.id),
            "status": content.status,
            "headline_short": content.headline_short,
            "headline_long": content.headline_long,
            "paraphrased_text": content.paraphrased_text,
            "similarity_score": content.similarity_score,
            "requires_hitl": content.requires_hitl,
            "created_at": content.created_at.isoformat() if content.created_at else None,
            "tags": content.tags
        }
        
        session.close()
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get content {content_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get content")


@app.post("/api/content/{content_id}/approve")
async def approve_content(content_id: str, background_tasks: BackgroundTasks):
    """Approve content for publishing (HITL)"""
    try:
        session = SessionLocal()
        
        from .models import ProcessedContent, ContentStatus
        
        content = session.query(ProcessedContent).filter(
            ProcessedContent.id == content_id
        ).first()
        
        if not content:
            session.close()
            raise HTTPException(status_code=404, detail="Content not found")
        
        if not content.requires_hitl:
            session.close()
            raise HTTPException(status_code=400, detail="Content does not require approval")
        
        # Update status
        content.status = ContentStatus.READY.value
        content.requires_hitl = False
        session.commit()
        session.close()
        
        # Queue for publishing
        redis_client = RedisClient()
        await redis_client.lpush(
            "content_publishing_queue",
            {
                "content_id": content_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        return {"message": "Content approved and queued for publishing"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve content {content_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve content")


@app.post("/api/content/{content_id}/reject")
async def reject_content(content_id: str):
    """Reject content (HITL)"""
    try:
        session = SessionLocal()
        
        from .models import ProcessedContent, ContentStatus
        
        content = session.query(ProcessedContent).filter(
            ProcessedContent.id == content_id
        ).first()
        
        if not content:
            session.close()
            raise HTTPException(status_code=404, detail="Content not found")
        
        # Update status
        content.status = ContentStatus.REJECTED.value
        content.requires_hitl = False
        session.commit()
        session.close()
        
        return {"message": "Content rejected"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reject content {content_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject content")


@app.get("/api/content/pending")
async def get_pending_content():
    """Get content pending HITL review"""
    try:
        session = SessionLocal()
        
        from .models import ProcessedContent
        
        pending_content = session.query(ProcessedContent).filter(
            ProcessedContent.requires_hitl == True,
            ProcessedContent.status == "pending"
        ).order_by(ProcessedContent.created_at.desc()).limit(20).all()
        
        result = []
        for content in pending_content:
            result.append({
                "id": str(content.id),
                "headline_short": content.headline_short,
                "headline_long": content.headline_long,
                "paraphrased_text": content.paraphrased_text[:200] + "..." if len(content.paraphrased_text or "") > 200 else content.paraphrased_text,
                "similarity_score": content.similarity_score,
                "risk_level": content.risk_level,
                "content_type": content.content_type,
                "created_at": content.created_at.isoformat() if content.created_at else None
            })
        
        session.close()
        return {"pending_content": result}
        
    except Exception as e:
        logger.error(f"Failed to get pending content: {e}")
        raise HTTPException(status_code=500, detail="Failed to get pending content")


@app.post("/api/manual/process")
async def manual_process_content(background_tasks: BackgroundTasks, limit: int = 10):
    """Manually trigger content processing"""
    try:
        # Add task to process raw content
        background_tasks.add_task(trigger_manual_processing, limit)
        return {"message": f"Manual processing triggered for up to {limit} items"}
        
    except Exception as e:
        logger.error(f"Manual processing trigger failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to trigger processing")


async def trigger_manual_processing(limit: int):
    """Background task to process unprocessed content"""
    try:
        session = SessionLocal()
        redis_client = RedisClient()
        
        from .models import RawContent
        
        # Get unprocessed content
        unprocessed = session.query(RawContent).filter(
            RawContent.processed == False
        ).limit(limit).all()
        
        for content in unprocessed:
            # Add to processing queue
            await redis_client.lpush(
                "content_processing_queue",
                {
                    "content_id": str(content.id),
                    "timestamp": datetime.utcnow().isoformat(),
                    "source": "manual"
                }
            )
        
        session.close()
        logger.info(f"Queued {len(unprocessed)} items for manual processing")
        
    except Exception as e:
        logger.error(f"Manual processing failed: {e}")


@app.get("/api/publishing/stats")
async def get_publishing_stats():
    """Get publishing statistics"""
    try:
        if publishing_service:
            stats = await publishing_service.get_publishing_stats()
            return stats
        else:
            raise HTTPException(status_code=503, detail="Publishing service not available")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get publishing stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get publishing statistics")


@app.get("/api/sources")
async def get_sources():
    """Get configured sources"""
    try:
        session = SessionLocal()
        
        from .models import Source
        
        sources = session.query(Source).all()
        
        result = []
        for source in sources:
            result.append({
                "id": source.id,
                "name": source.name,
                "platform": source.platform,
                "username": source.username,
                "weight": source.weight,
                "is_active": source.is_active,
                "last_checked": source.last_checked.isoformat() if source.last_checked else None
            })
        
        session.close()
        return {"sources": result}
        
    except Exception as e:
        logger.error(f"Failed to get sources: {e}")
        raise HTTPException(status_code=500, detail="Failed to get sources")


# Error handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


def main():
    """Main entry point"""
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )


if __name__ == "__main__":
    main()
