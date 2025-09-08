"""
Publishing service for Telegram and other platforms
"""
import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import aiohttp
from telegram import Bot, InputMediaPhoto
from telegram.error import TelegramError

from ..config import settings, affiliate_config
from ..models import SessionLocal, ProcessedContent, PublishedPost, ContentStatus
from ..utils.redis_client import RedisClient
from ..utils.image_generation import ImageGenerationService

logger = logging.getLogger(__name__)


class PublishingService:
    """Content publishing service"""
    
    def __init__(self):
        self.session = SessionLocal()
        self.redis_client = RedisClient()
        self.image_service = ImageGenerationService()
        
        # Initialize Telegram bot
        self.telegram_bot = None
        if settings.telegram_bot_token:
            try:
                self.telegram_bot = Bot(token=settings.telegram_bot_token)
                logger.info("Telegram bot initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Telegram bot: {e}")
    
    async def process_publishing_queue(self):
        """Process publishing queue continuously"""
        try:
            while True:
                # Get next item from queue
                queue_item = await self.redis_client.brpop("content_publishing_queue", timeout=30)
                
                if queue_item:
                    try:
                        content_id = queue_item["content_id"]
                        await self.publish_content(content_id)
                    except Exception as e:
                        logger.error(f"Failed to publish content {queue_item}: {e}")
                
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Publishing queue error: {e}")
    
    async def publish_content(self, processed_content_id: str) -> bool:
        """Publish a single piece of processed content"""
        try:
            # Get processed content
            processed_content = self.session.query(ProcessedContent).filter(
                ProcessedContent.id == processed_content_id
            ).first()
            
            if not processed_content:
                logger.warning(f"Processed content {processed_content_id} not found")
                return False
            
            if processed_content.status != ContentStatus.READY.value:
                logger.warning(f"Content {processed_content_id} not ready for publishing")
                return False
            
            # Check if already published
            existing_post = self.session.query(PublishedPost).filter(
                PublishedPost.processed_content_id == processed_content_id
            ).first()
            
            if existing_post:
                logger.info(f"Content {processed_content_id} already published")
                return True
            
            logger.info(f"Publishing content {processed_content_id}")
            
            # Generate final post content
            final_content = await self._prepare_final_content(processed_content)
            
            # Generate/get images
            image_urls = await self._prepare_images(processed_content)
            
            # Publish to Telegram
            success = await self._publish_to_telegram(processed_content, final_content, image_urls)
            
            if success:
                # Update status
                processed_content.status = ContentStatus.PUBLISHED.value
                self.session.commit()
                
                logger.info(f"Successfully published content {processed_content_id}")
                return True
            else:
                logger.error(f"Failed to publish content {processed_content_id}")
                return False
                
        except Exception as e:
            logger.error(f"Publishing failed for content {processed_content_id}: {e}")
            self.session.rollback()
            return False
    
    async def _prepare_final_content(self, processed_content: ProcessedContent) -> Dict[str, Any]:
        """Prepare final content for publishing"""
        try:
            # Decide which headline to use
            headline = processed_content.headline_short or processed_content.headline_long or "Новости криптовалют"
            
            # Use paraphrased text or translated text as fallback
            main_text = processed_content.paraphrased_text or processed_content.translated_text
            
            # Add author note if available
            if processed_content.author_note:
                main_text += f"\n\n💬 {processed_content.author_note}"
            
            # Add affiliate link if needed
            affiliate_info = await self._should_add_affiliate_link()
            if affiliate_info:
                main_text += f"\n\n{affiliate_info['text']}"
                main_text += f"\n\n⚠️ {affiliate_config.DISCLOSURE_TEXT}"
            
            # Add tags
            tags = processed_content.tags or []
            if tags:
                hashtags = " ".join([f"#{tag}" for tag in tags[:3]])  # Limit to 3 tags
                main_text += f"\n\n{hashtags}"
            
            return {
                "headline": headline,
                "text": main_text,
                "contains_affiliate": bool(affiliate_info),
                "affiliate_link_id": affiliate_info["name"] if affiliate_info else None
            }
            
        except Exception as e:
            logger.error(f"Failed to prepare final content: {e}")
            return {
                "headline": "Новости криптовалют",
                "text": processed_content.translated_text or "Контент недоступен",
                "contains_affiliate": False,
                "affiliate_link_id": None
            }
    
    async def _should_add_affiliate_link(self) -> Optional[Dict[str, Any]]:
        """Determine if affiliate link should be added"""
        try:
            # Check recent posts to see if we should add affiliate link
            recent_posts = self.session.query(PublishedPost).filter(
                PublishedPost.published_at >= datetime.utcnow() - timedelta(hours=24)
            ).order_by(PublishedPost.published_at.desc()).limit(settings.affiliate_link_frequency).all()
            
            # Count posts with affiliate links
            affiliate_posts = [post for post in recent_posts if post.contains_affiliate]
            
            # If less than 1 in N posts have affiliate links, add one
            if len(affiliate_posts) == 0 or len(recent_posts) % settings.affiliate_link_frequency == 0:
                # Choose random affiliate link based on weights
                import random
                
                total_weight = sum(link["weight"] for link in affiliate_config.AFFILIATE_LINKS)
                random_value = random.uniform(0, total_weight)
                
                current_weight = 0
                for link in affiliate_config.AFFILIATE_LINKS:
                    current_weight += link["weight"]
                    if random_value <= current_weight:
                        return link
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to check affiliate link eligibility: {e}")
            return None
    
    async def _prepare_images(self, processed_content: ProcessedContent) -> List[str]:
        """Prepare images for publishing"""
        try:
            # Get existing images for this content
            from ..models import GeneratedImage
            
            existing_images = self.session.query(GeneratedImage).filter(
                GeneratedImage.processed_content_id == processed_content.id
            ).all()
            
            if existing_images:
                return [img.image_url for img in existing_images if img.image_url]
            
            # Generate new image if none exist
            headline = processed_content.headline_short or processed_content.headline_long
            if headline:
                image_url = await self.image_service.generate_post_image(
                    str(processed_content.id),
                    headline,
                    processed_content.content_type
                )
                
                if image_url:
                    return [image_url]
            
            return []
            
        except Exception as e:
            logger.error(f"Failed to prepare images: {e}")
            return []
    
    async def _publish_to_telegram(
        self, 
        processed_content: ProcessedContent, 
        final_content: Dict[str, Any], 
        image_urls: List[str]
    ) -> bool:
        """Publish content to Telegram channel"""
        try:
            if not self.telegram_bot:
                logger.error("Telegram bot not initialized")
                return False
            
            # Prepare message text
            message_text = f"**{final_content['headline']}**\n\n{final_content['text']}"
            
            # Telegram message length limit
            if len(message_text) > 4096:
                message_text = message_text[:4093] + "..."
            
            message_id = None
            
            # Send with image if available
            if image_urls:
                try:
                    # Download image for Telegram
                    async with aiohttp.ClientSession() as session:
                        async with session.get(image_urls[0]) as response:
                            if response.status == 200:
                                image_data = await response.read()
                                
                                # Send photo with caption
                                message = await self.telegram_bot.send_photo(
                                    chat_id=settings.telegram_channel_id,
                                    photo=image_data,
                                    caption=message_text,
                                    parse_mode='Markdown'
                                )
                                message_id = message.message_id
                except Exception as e:
                    logger.warning(f"Failed to send with image, sending text only: {e}")
            
            # Send as text message if image failed or no image
            if not message_id:
                message = await self.telegram_bot.send_message(
                    chat_id=settings.telegram_channel_id,
                    text=message_text,
                    parse_mode='Markdown'
                )
                message_id = message.message_id
            
            # Record published post
            published_post = PublishedPost(
                processed_content_id=processed_content.id,
                platform="telegram",
                external_post_id=str(message_id),
                channel_id=settings.telegram_channel_id,
                final_text=final_content["text"],
                final_images=image_urls,
                headline_used=final_content["headline"],
                tags_used=processed_content.tags or [],
                contains_affiliate=final_content["contains_affiliate"],
                affiliate_link_id=final_content["affiliate_link_id"],
                published_at=datetime.utcnow()
            )
            
            self.session.add(published_post)
            self.session.commit()
            
            logger.info(f"Published to Telegram: message {message_id}")
            return True
            
        except TelegramError as e:
            logger.error(f"Telegram publishing error: {e}")
            return False
        except Exception as e:
            logger.error(f"Publishing to Telegram failed: {e}")
            return False
    
    async def schedule_post(self, processed_content_id: str, publish_at: datetime) -> bool:
        """Schedule a post for future publishing"""
        try:
            # Add to scheduled queue
            await self.redis_client.lpush(
                "scheduled_posts_queue",
                json.dumps({
                    "content_id": processed_content_id,
                    "publish_at": publish_at.isoformat(),
                    "scheduled_at": datetime.utcnow().isoformat()
                })
            )
            
            logger.info(f"Scheduled content {processed_content_id} for {publish_at}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to schedule post: {e}")
            return False
    
    async def process_scheduled_posts(self):
        """Process scheduled posts that are ready to publish"""
        try:
            # Get all scheduled posts
            scheduled_posts = await self.redis_client.smembers("scheduled_posts_queue")
            
            current_time = datetime.utcnow()
            
            for post_data in scheduled_posts:
                try:
                    post_info = json.loads(post_data)
                    publish_time = datetime.fromisoformat(post_info["publish_at"])
                    
                    # Check if it's time to publish
                    if current_time >= publish_time:
                        # Remove from scheduled queue
                        await self.redis_client.srem("scheduled_posts_queue", post_data)
                        
                        # Add to publishing queue
                        await self.redis_client.lpush(
                            "content_publishing_queue",
                            json.dumps({
                                "content_id": post_info["content_id"],
                                "timestamp": current_time.isoformat()
                            })
                        )
                        
                        logger.info(f"Moved scheduled post {post_info['content_id']} to publishing queue")
                        
                except Exception as e:
                    logger.error(f"Failed to process scheduled post {post_data}: {e}")
            
        except Exception as e:
            logger.error(f"Failed to process scheduled posts: {e}")
    
    async def update_post_metrics(self, published_post_id: str) -> bool:
        """Update metrics for a published post"""
        try:
            published_post = self.session.query(PublishedPost).get(published_post_id)
            if not published_post:
                return False
            
            if published_post.platform == "telegram" and self.telegram_bot:
                try:
                    # Get message info from Telegram
                    # Note: This requires the bot to have admin rights in the channel
                    # For public channels, you might need to use different approaches
                    
                    # For now, we'll just update the timestamp
                    published_post.last_metrics_update = datetime.utcnow()
                    self.session.commit()
                    
                    return True
                    
                except Exception as e:
                    logger.warning(f"Failed to get Telegram metrics: {e}")
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to update post metrics: {e}")
            return False
    
    async def get_publishing_stats(self) -> Dict[str, Any]:
        """Get publishing statistics"""
        try:
            # Get stats from last 30 days
            from datetime import timedelta
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            
            recent_posts = self.session.query(PublishedPost).filter(
                PublishedPost.published_at >= cutoff_date
            ).all()
            
            stats = {
                "total_posts": len(recent_posts),
                "posts_with_affiliate": len([p for p in recent_posts if p.contains_affiliate]),
                "platforms": {},
                "daily_posts": {},
                "avg_engagement": 0.0
            }
            
            # Count by platform
            for post in recent_posts:
                platform = post.platform
                stats["platforms"][platform] = stats["platforms"].get(platform, 0) + 1
            
            # Count by day
            for post in recent_posts:
                day = post.published_at.date().isoformat()
                stats["daily_posts"][day] = stats["daily_posts"].get(day, 0) + 1
            
            # Calculate average engagement
            total_engagement = sum(
                post.likes_count + post.shares_count + post.comments_count 
                for post in recent_posts
            )
            if recent_posts:
                stats["avg_engagement"] = total_engagement / len(recent_posts)
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get publishing stats: {e}")
            return {}
    
    def close(self):
        """Close connections"""
        self.session.close()
        self.image_service.close()


# Standalone functions for scheduled tasks
async def run_publishing_service():
    """Run publishing service continuously"""
    service = PublishingService()
    try:
        # Start both publishing and scheduling processors
        await asyncio.gather(
            service.process_publishing_queue(),
            periodic_schedule_check(service)
        )
    except KeyboardInterrupt:
        logger.info("Stopping publishing service...")
    except Exception as e:
        logger.error(f"Publishing service error: {e}")
    finally:
        service.close()


async def periodic_schedule_check(service: PublishingService):
    """Periodically check for scheduled posts"""
    while True:
        try:
            await service.process_scheduled_posts()
            await asyncio.sleep(60)  # Check every minute
        except Exception as e:
            logger.error(f"Scheduled posts check error: {e}")
            await asyncio.sleep(60)


async def publish_single_content(content_id: str) -> bool:
    """Publish a single piece of content"""
    service = PublishingService()
    try:
        return await service.publish_content(content_id)
    finally:
        service.close()


if __name__ == "__main__":
    # Test publishing service
    asyncio.run(run_publishing_service())
