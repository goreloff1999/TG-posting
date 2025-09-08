"""
Telegram content ingestion module
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from langdetect import detect
import json

from ..config import settings, source_config
from ..models import SessionLocal, Source, RawContent
from ..utils.redis_client import RedisClient

logger = logging.getLogger(__name__)


class TelegramIngestion:
    """Telegram content ingestion service"""
    
    def __init__(self):
        self.client = TelegramClient(
            'session_name',
            settings.telegram_api_id,
            settings.telegram_api_hash
        )
        self.redis_client = RedisClient()
        self.session = SessionLocal()
        
    async def start(self):
        """Start Telegram client and monitoring"""
        try:
            await self.client.start()
            logger.info("Telegram client started successfully")
            
            # Initialize sources in database
            await self._initialize_sources()
            
            # Start monitoring channels
            await self._start_monitoring()
            
        except Exception as e:
            logger.error(f"Failed to start Telegram ingestion: {e}")
            raise
    
    async def stop(self):
        """Stop Telegram client"""
        try:
            await self.client.disconnect()
            self.session.close()
            logger.info("Telegram client stopped")
        except Exception as e:
            logger.error(f"Error stopping Telegram client: {e}")
    
    async def _initialize_sources(self):
        """Initialize Telegram sources in database"""
        try:
            for channel in source_config.TELEGRAM_CHANNELS:
                # Check if source already exists
                existing = self.session.query(Source).filter(
                    Source.platform == "telegram",
                    Source.username == channel
                ).first()
                
                if not existing:
                    source = Source(
                        name=f"Telegram {channel}",
                        platform="telegram",
                        username=channel,
                        weight=source_config.SOURCE_WEIGHTS.get(channel, 1.0),
                        is_active=True
                    )
                    self.session.add(source)
            
            self.session.commit()
            logger.info(f"Initialized {len(source_config.TELEGRAM_CHANNELS)} Telegram sources")
            
        except Exception as e:
            logger.error(f"Failed to initialize sources: {e}")
            self.session.rollback()
    
    async def _start_monitoring(self):
        """Start monitoring configured channels"""
        try:
            # Add event handler for new messages
            @self.client.on(events.NewMessage)
            async def handler(event):
                await self._process_new_message(event)
            
            # Historical data collection for each channel
            for channel in source_config.TELEGRAM_CHANNELS:
                try:
                    await self._collect_historical_data(channel)
                except Exception as e:
                    logger.error(f"Failed to collect historical data for {channel}: {e}")
            
            logger.info("Started monitoring Telegram channels")
            
        except Exception as e:
            logger.error(f"Failed to start monitoring: {e}")
    
    async def _collect_historical_data(self, channel: str, limit: int = 50):
        """Collect recent historical data from channel"""
        try:
            source = self.session.query(Source).filter(
                Source.platform == "telegram",
                Source.username == channel
            ).first()
            
            if not source:
                logger.warning(f"Source not found for channel {channel}")
                return
            
            # Get recent messages
            async for message in self.client.iter_messages(channel, limit=limit):
                if message.message:  # Only text messages for now
                    await self._process_message(message, source)
            
            # Update last checked time
            source.last_checked = datetime.utcnow()
            self.session.commit()
            
            logger.info(f"Collected historical data for {channel}")
            
        except Exception as e:
            logger.error(f"Failed to collect historical data for {channel}: {e}")
    
    async def _process_new_message(self, event):
        """Process new incoming message"""
        try:
            # Get channel info
            chat = await event.get_chat()
            channel_username = getattr(chat, 'username', None)
            
            if not channel_username:
                return  # Skip if no username
            
            channel_username = f"@{channel_username}"
            
            # Check if we're monitoring this channel
            if channel_username not in source_config.TELEGRAM_CHANNELS:
                return
            
            # Get source from database
            source = self.session.query(Source).filter(
                Source.platform == "telegram",
                Source.username == channel_username
            ).first()
            
            if not source:
                logger.warning(f"Source not found for {channel_username}")
                return
            
            await self._process_message(event.message, source)
            
        except Exception as e:
            logger.error(f"Failed to process new message: {e}")
    
    async def _process_message(self, message, source: Source):
        """Process individual message"""
        try:
            # Skip if no text content
            if not message.message:
                return
            
            # Check for duplicates
            existing = self.session.query(RawContent).filter(
                RawContent.source_id == source.id,
                RawContent.external_id == str(message.id)
            ).first()
            
            if existing:
                return  # Already processed
            
            # Extract media URLs
            media_urls = []
            if message.media:
                if isinstance(message.media, (MessageMediaPhoto, MessageMediaDocument)):
                    # Note: In production, you'd download and store media
                    media_urls.append(f"telegram_media_{message.id}")
            
            # Detect language
            try:
                language = detect(message.message)
            except:
                language = "unknown"
            
            # Create raw content record
            raw_content = RawContent(
                source_id=source.id,
                external_id=str(message.id),
                text=message.message,
                media_urls=media_urls,
                author=getattr(message.sender, 'username', 'unknown') if message.sender else 'unknown',
                published_at=message.date,
                views_count=getattr(message, 'views', 0),
                language=language,
                metadata={
                    'forwards': getattr(message, 'forwards', 0),
                    'replies': getattr(message.replies, 'replies', 0) if message.replies else 0,
                    'message_type': 'text',
                    'has_media': bool(message.media)
                }
            )
            
            self.session.add(raw_content)
            self.session.commit()
            
            # Add to processing queue
            await self._queue_for_processing(raw_content.id)
            
            logger.info(f"Processed message {message.id} from {source.username}")
            
        except Exception as e:
            logger.error(f"Failed to process message {message.id}: {e}")
            self.session.rollback()
    
    async def _queue_for_processing(self, content_id: str):
        """Add content to processing queue"""
        try:
            # Add to Redis queue for processing
            await self.redis_client.lpush(
                "content_processing_queue",
                json.dumps({
                    "content_id": str(content_id),
                    "timestamp": datetime.utcnow().isoformat(),
                    "source": "telegram"
                })
            )
            
            logger.debug(f"Queued content {content_id} for processing")
            
        except Exception as e:
            logger.error(f"Failed to queue content {content_id}: {e}")
    
    async def get_channel_info(self, channel: str) -> Optional[Dict[str, Any]]:
        """Get information about a channel"""
        try:
            entity = await self.client.get_entity(channel)
            
            return {
                'id': entity.id,
                'title': getattr(entity, 'title', ''),
                'username': getattr(entity, 'username', ''),
                'participants_count': getattr(entity, 'participants_count', 0),
                'about': getattr(entity, 'about', ''),
                'verified': getattr(entity, 'verified', False)
            }
            
        except Exception as e:
            logger.error(f"Failed to get channel info for {channel}: {e}")
            return None
    
    async def search_messages(self, channel: str, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Search messages in a channel"""
        try:
            messages = []
            
            async for message in self.client.iter_messages(channel, search=query, limit=limit):
                if message.message:
                    messages.append({
                        'id': message.id,
                        'text': message.message,
                        'date': message.date.isoformat(),
                        'views': getattr(message, 'views', 0),
                        'forwards': getattr(message, 'forwards', 0)
                    })
            
            return messages
            
        except Exception as e:
            logger.error(f"Failed to search messages in {channel}: {e}")
            return []


# Standalone functions for scheduled tasks
async def run_telegram_ingestion():
    """Run Telegram ingestion service"""
    ingestion = TelegramIngestion()
    try:
        await ingestion.start()
        
        # Keep running until interrupted
        while True:
            await asyncio.sleep(60)  # Check every minute
            
    except KeyboardInterrupt:
        logger.info("Stopping Telegram ingestion...")
    except Exception as e:
        logger.error(f"Telegram ingestion error: {e}")
    finally:
        await ingestion.stop()


async def collect_missed_content():
    """Collect any missed content from recent period"""
    ingestion = TelegramIngestion()
    try:
        await ingestion.start()
        
        # Collect last 24 hours of content
        for channel in source_config.TELEGRAM_CHANNELS:
            await ingestion._collect_historical_data(channel, limit=200)
        
    except Exception as e:
        logger.error(f"Failed to collect missed content: {e}")
    finally:
        await ingestion.stop()


if __name__ == "__main__":
    # For testing
    asyncio.run(run_telegram_ingestion())
