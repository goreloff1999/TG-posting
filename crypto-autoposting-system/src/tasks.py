"""
Celery tasks for background processing
"""
import logging
from datetime import datetime, timedelta
from celery import Celery
from celery.schedules import crontab

from .config import settings
from .ingestion.telegram_ingestion import collect_missed_content
from .ingestion.twitter_ingestion import search_crypto_trends
from .processing.content_processor import run_content_processor
from .publishing.publisher import run_publishing_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Celery instance
celery_app = Celery(
    'crypto_autoposting',
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=['src.tasks']
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    result_expires=3600,
    task_routes={
        'src.tasks.collect_telegram_content': {'queue': 'ingestion'},
        'src.tasks.collect_twitter_content': {'queue': 'ingestion'},
        'src.tasks.process_content': {'queue': 'processing'},
        'src.tasks.publish_content': {'queue': 'publishing'},
        'src.tasks.cleanup_old_data': {'queue': 'maintenance'},
    }
)

# Schedule periodic tasks
celery_app.conf.beat_schedule = {
    # Content ingestion every 15 minutes
    'collect-telegram-content': {
        'task': 'src.tasks.collect_telegram_content',
        'schedule': crontab(minute='*/15'),
    },
    'collect-twitter-content': {
        'task': 'src.tasks.collect_twitter_content',
        'schedule': crontab(minute='*/30'),
    },
    
    # Content processing every 5 minutes
    'process-content': {
        'task': 'src.tasks.process_content',
        'schedule': crontab(minute='*/5'),
    },
    
    # Publishing every 10 minutes
    'publish-content': {
        'task': 'src.tasks.publish_content',
        'schedule': crontab(minute='*/10'),
    },
    
    # Maintenance tasks
    'cleanup-old-data': {
        'task': 'src.tasks.cleanup_old_data',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
    'update-metrics': {
        'task': 'src.tasks.update_metrics',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
    },
    
    # Quality checks
    'quality-check': {
        'task': 'src.tasks.quality_check',
        'schedule': crontab(hour='*/6'),  # Every 6 hours
    }
}


@celery_app.task(bind=True, max_retries=3)
def collect_telegram_content(self):
    """Collect content from Telegram channels"""
    try:
        logger.info("Starting Telegram content collection")
        
        # Import here to avoid circular imports
        import asyncio
        asyncio.run(collect_missed_content())
        
        logger.info("Telegram content collection completed")
        return {"status": "success", "timestamp": datetime.utcnow().isoformat()}
        
    except Exception as e:
        logger.error(f"Telegram content collection failed: {e}")
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


@celery_app.task(bind=True, max_retries=3)
def collect_twitter_content(self):
    """Collect content from Twitter/X"""
    try:
        logger.info("Starting Twitter content collection")
        
        import asyncio
        asyncio.run(search_crypto_trends())
        
        logger.info("Twitter content collection completed")
        return {"status": "success", "timestamp": datetime.utcnow().isoformat()}
        
    except Exception as e:
        logger.error(f"Twitter content collection failed: {e}")
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


@celery_app.task(bind=True, max_retries=3)
def process_content(self):
    """Process queued content"""
    try:
        logger.info("Starting content processing")
        
        from .processing.content_processor import ContentProcessor
        from .utils.redis_client import RedisClient
        import asyncio
        
        async def process_batch():
            processor = ContentProcessor()
            redis_client = RedisClient()
            
            try:
                # Process up to 10 items at a time
                processed_count = 0
                max_items = 10
                
                for _ in range(max_items):
                    queue_item = await redis_client.brpop("content_processing_queue", timeout=5)
                    if queue_item:
                        content_id = queue_item["content_id"]
                        await processor.process_single_content(content_id)
                        processed_count += 1
                    else:
                        break  # No more items in queue
                
                return processed_count
                
            finally:
                processor.close()
        
        processed_count = asyncio.run(process_batch())
        
        logger.info(f"Content processing completed: {processed_count} items processed")
        return {
            "status": "success", 
            "processed_count": processed_count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Content processing failed: {e}")
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


@celery_app.task(bind=True, max_retries=3)
def publish_content(self):
    """Publish ready content"""
    try:
        logger.info("Starting content publishing")
        
        from .publishing.publisher import PublishingService
        from .utils.redis_client import RedisClient
        import asyncio
        
        async def publish_batch():
            publisher = PublishingService()
            redis_client = RedisClient()
            
            try:
                # Process scheduled posts first
                await publisher.process_scheduled_posts()
                
                # Publish up to 5 items at a time
                published_count = 0
                max_items = 5
                
                for _ in range(max_items):
                    queue_item = await redis_client.brpop("content_publishing_queue", timeout=5)
                    if queue_item:
                        content_id = queue_item["content_id"]
                        success = await publisher.publish_content(content_id)
                        if success:
                            published_count += 1
                    else:
                        break  # No more items in queue
                
                return published_count
                
            finally:
                publisher.close()
        
        published_count = asyncio.run(publish_batch())
        
        logger.info(f"Content publishing completed: {published_count} items published")
        return {
            "status": "success",
            "published_count": published_count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Content publishing failed: {e}")
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


@celery_app.task
def cleanup_old_data():
    """Clean up old data from database and storage"""
    try:
        logger.info("Starting data cleanup")
        
        from .models import SessionLocal, RawContent, ProcessedContent, PublishedPost
        from .utils.storage import StorageService
        import asyncio
        
        session = SessionLocal()
        storage = StorageService()
        
        try:
            # Clean up old raw content (older than 30 days)
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            
            old_raw_content = session.query(RawContent).filter(
                RawContent.created_at < cutoff_date,
                RawContent.processed == True
            ).all()
            
            deleted_raw = 0
            for content in old_raw_content:
                session.delete(content)
                deleted_raw += 1
                
                if deleted_raw % 100 == 0:
                    session.commit()
            
            session.commit()
            
            # Clean up old files in storage
            asyncio.run(storage.cleanup_old_files(days_old=30))
            
            logger.info(f"Data cleanup completed: {deleted_raw} raw content items deleted")
            return {
                "status": "success",
                "deleted_raw_content": deleted_raw,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Data cleanup failed: {e}")
        return {"status": "error", "error": str(e)}


@celery_app.task
def update_metrics():
    """Update system metrics"""
    try:
        logger.info("Updating system metrics")
        
        from .models import SessionLocal, SystemMetrics, RawContent, ProcessedContent, PublishedPost
        
        session = SessionLocal()
        
        try:
            # Calculate metrics
            now = datetime.utcnow()
            hour_ago = now - timedelta(hours=1)
            day_ago = now - timedelta(days=1)
            
            metrics_to_save = []
            
            # Content metrics
            metrics_to_save.append(SystemMetrics(
                metric_name="content_ingested_hourly",
                metric_value=session.query(RawContent).filter(
                    RawContent.created_at >= hour_ago
                ).count(),
                timestamp=now,
                period="hourly"
            ))
            
            metrics_to_save.append(SystemMetrics(
                metric_name="content_processed_hourly",
                metric_value=session.query(ProcessedContent).filter(
                    ProcessedContent.created_at >= hour_ago
                ).count(),
                timestamp=now,
                period="hourly"
            ))
            
            metrics_to_save.append(SystemMetrics(
                metric_name="content_published_hourly",
                metric_value=session.query(PublishedPost).filter(
                    PublishedPost.published_at >= hour_ago
                ).count(),
                timestamp=now,
                period="hourly"
            ))
            
            # Quality metrics
            total_processed = session.query(ProcessedContent).filter(
                ProcessedContent.created_at >= day_ago
            ).count()
            
            if total_processed > 0:
                hitl_required = session.query(ProcessedContent).filter(
                    ProcessedContent.created_at >= day_ago,
                    ProcessedContent.requires_hitl == True
                ).count()
                
                hitl_rate = hitl_required / total_processed
                
                metrics_to_save.append(SystemMetrics(
                    metric_name="hitl_rate_daily",
                    metric_value=hitl_rate,
                    timestamp=now,
                    period="daily"
                ))
            
            # Save metrics
            for metric in metrics_to_save:
                session.add(metric)
            
            session.commit()
            
            logger.info(f"System metrics updated: {len(metrics_to_save)} metrics saved")
            return {
                "status": "success",
                "metrics_count": len(metrics_to_save),
                "timestamp": now.isoformat()
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Metrics update failed: {e}")
        return {"status": "error", "error": str(e)}


@celery_app.task
def quality_check():
    """Perform quality checks on recent content"""
    try:
        logger.info("Starting quality check")
        
        from .models import SessionLocal, ProcessedContent, PublishedPost
        
        session = SessionLocal()
        
        try:
            # Check recent content quality
            day_ago = datetime.utcnow() - timedelta(days=1)
            
            recent_content = session.query(ProcessedContent).filter(
                ProcessedContent.created_at >= day_ago,
                ProcessedContent.status == "published"
            ).all()
            
            quality_issues = []
            
            for content in recent_content:
                # Check for quality issues
                issues = []
                
                # Check text length
                if not content.paraphrased_text or len(content.paraphrased_text) < 100:
                    issues.append("Text too short")
                
                # Check similarity score
                if content.similarity_score > 0.8:
                    issues.append("High similarity score")
                
                # Check headline
                if not content.headline_short and not content.headline_long:
                    issues.append("Missing headline")
                
                if issues:
                    quality_issues.append({
                        "content_id": str(content.id),
                        "issues": issues
                    })
            
            logger.info(f"Quality check completed: {len(quality_issues)} issues found")
            return {
                "status": "success",
                "total_checked": len(recent_content),
                "issues_found": len(quality_issues),
                "issues": quality_issues[:10],  # Return first 10 issues
                "timestamp": datetime.utcnow().isoformat()
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Quality check failed: {e}")
        return {"status": "error", "error": str(e)}


@celery_app.task
def process_single_content_task(content_id: str):
    """Process a single piece of content"""
    try:
        from .processing.content_processor import ContentProcessor
        import asyncio
        
        async def process():
            processor = ContentProcessor()
            try:
                await processor.process_single_content(content_id)
                return True
            finally:
                processor.close()
        
        success = asyncio.run(process())
        
        return {
            "status": "success" if success else "failed",
            "content_id": content_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Single content processing failed for {content_id}: {e}")
        return {"status": "error", "content_id": content_id, "error": str(e)}


@celery_app.task
def publish_single_content_task(content_id: str):
    """Publish a single piece of content"""
    try:
        from .publishing.publisher import PublishingService
        import asyncio
        
        async def publish():
            publisher = PublishingService()
            try:
                return await publisher.publish_content(content_id)
            finally:
                publisher.close()
        
        success = asyncio.run(publish())
        
        return {
            "status": "success" if success else "failed",
            "content_id": content_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Single content publishing failed for {content_id}: {e}")
        return {"status": "error", "content_id": content_id, "error": str(e)}


# Health check task
@celery_app.task
def health_check():
    """Health check task for monitoring"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "worker_id": health_check.request.id
    }


if __name__ == "__main__":
    celery_app.start()
