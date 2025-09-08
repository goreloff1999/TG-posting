"""
Twitter/X content ingestion module
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import tweepy
from langdetect import detect
import json

from ..config import settings, source_config
from ..models import SessionLocal, Source, RawContent
from ..utils.redis_client import RedisClient

logger = logging.getLogger(__name__)


class TwitterIngestion:
    """Twitter/X content ingestion service"""
    
    def __init__(self):
        self.api = None
        self.client = None
        self.redis_client = RedisClient()
        self.session = SessionLocal()
        self._initialize_twitter_client()
        
    def _initialize_twitter_client(self):
        """Initialize Twitter API client"""
        try:
            if not all([
                settings.twitter_api_key,
                settings.twitter_api_secret,
                settings.twitter_access_token,
                settings.twitter_access_token_secret
            ]):
                logger.warning("Twitter API credentials not configured")
                return
            
            # Initialize Tweepy client
            auth = tweepy.OAuthHandler(
                settings.twitter_api_key,
                settings.twitter_api_secret
            )
            auth.set_access_token(
                settings.twitter_access_token,
                settings.twitter_access_token_secret
            )
            
            self.api = tweepy.API(auth, wait_on_rate_limit=True)
            
            # Also initialize v2 client for enhanced features
            self.client = tweepy.Client(
                consumer_key=settings.twitter_api_key,
                consumer_secret=settings.twitter_api_secret,
                access_token=settings.twitter_access_token,
                access_token_secret=settings.twitter_access_token_secret,
                wait_on_rate_limit=True
            )
            
            logger.info("Twitter API client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Twitter client: {e}")
    
    async def start(self):
        """Start Twitter monitoring"""
        try:
            if not self.api or not self.client:
                logger.error("Twitter API not initialized")
                return
            
            # Initialize sources in database
            await self._initialize_sources()
            
            # Start monitoring accounts
            await self._start_monitoring()
            
        except Exception as e:
            logger.error(f"Failed to start Twitter ingestion: {e}")
            raise
    
    async def stop(self):
        """Stop Twitter monitoring"""
        try:
            self.session.close()
            logger.info("Twitter ingestion stopped")
        except Exception as e:
            logger.error(f"Error stopping Twitter ingestion: {e}")
    
    async def _initialize_sources(self):
        """Initialize Twitter sources in database"""
        try:
            for account in source_config.TWITTER_ACCOUNTS:
                # Check if source already exists
                existing = self.session.query(Source).filter(
                    Source.platform == "twitter",
                    Source.username == account
                ).first()
                
                if not existing:
                    source = Source(
                        name=f"Twitter @{account}",
                        platform="twitter",
                        username=account,
                        weight=source_config.SOURCE_WEIGHTS.get(account, 1.0),
                        is_active=True
                    )
                    self.session.add(source)
            
            self.session.commit()
            logger.info(f"Initialized {len(source_config.TWITTER_ACCOUNTS)} Twitter sources")
            
        except Exception as e:
            logger.error(f"Failed to initialize Twitter sources: {e}")
            self.session.rollback()
    
    async def _start_monitoring(self):
        """Start monitoring configured accounts"""
        try:
            # Collect historical data for each account
            for account in source_config.TWITTER_ACCOUNTS:
                try:
                    await self._collect_user_tweets(account)
                except Exception as e:
                    logger.error(f"Failed to collect tweets for @{account}: {e}")
            
            logger.info("Started monitoring Twitter accounts")
            
        except Exception as e:
            logger.error(f"Failed to start Twitter monitoring: {e}")
    
    async def _collect_user_tweets(self, username: str, count: int = 50):
        """Collect recent tweets from a user"""
        try:
            source = self.session.query(Source).filter(
                Source.platform == "twitter",
                Source.username == username
            ).first()
            
            if not source:
                logger.warning(f"Source not found for @{username}")
                return
            
            # Get user tweets using v2 API
            user = self.client.get_user(username=username)
            if not user.data:
                logger.warning(f"User @{username} not found")
                return
            
            tweets = self.client.get_users_tweets(
                id=user.data.id,
                max_results=min(count, 100),
                tweet_fields=['created_at', 'public_metrics', 'context_annotations', 'lang'],
                exclude=['retweets', 'replies']  # Focus on original tweets
            )
            
            if not tweets.data:
                logger.info(f"No tweets found for @{username}")
                return
            
            for tweet in tweets.data:
                await self._process_tweet(tweet, source, user.data)
            
            # Update last checked time
            source.last_checked = datetime.utcnow()
            self.session.commit()
            
            logger.info(f"Collected {len(tweets.data)} tweets for @{username}")
            
        except Exception as e:
            logger.error(f"Failed to collect tweets for @{username}: {e}")
    
    async def _process_tweet(self, tweet, source: Source, user_data):
        """Process individual tweet"""
        try:
            # Check for duplicates
            existing = self.session.query(RawContent).filter(
                RawContent.source_id == source.id,
                RawContent.external_id == str(tweet.id)
            ).first()
            
            if existing:
                return  # Already processed
            
            # Skip if tweet is too short or not crypto-related
            if len(tweet.text) < 20:
                return
            
            # Basic crypto keywords filter
            crypto_keywords = [
                'bitcoin', 'btc', 'ethereum', 'eth', 'crypto', 'blockchain',
                'defi', 'nft', 'token', 'coin', 'trading', 'binance',
                'coinbase', 'price', 'market', 'bull', 'bear', 'hodl'
            ]
            
            if not any(keyword in tweet.text.lower() for keyword in crypto_keywords):
                return  # Not crypto-related
            
            # Extract metrics
            metrics = tweet.public_metrics if hasattr(tweet, 'public_metrics') else {}
            
            # Detect language
            language = getattr(tweet, 'lang', 'unknown')
            if language == 'unknown':
                try:
                    language = detect(tweet.text)
                except:
                    language = 'unknown'
            
            # Extract context annotations (topics)
            context_annotations = getattr(tweet, 'context_annotations', [])
            topics = []
            if context_annotations:
                topics = [ann.get('entity', {}).get('name', '') for ann in context_annotations]
            
            # Create raw content record
            raw_content = RawContent(
                source_id=source.id,
                external_id=str(tweet.id),
                text=tweet.text,
                media_urls=[],  # TODO: Extract media URLs if present
                author=user_data.username,
                published_at=tweet.created_at,
                reactions_count=metrics.get('like_count', 0),
                views_count=metrics.get('impression_count', 0),
                language=language,
                metadata={
                    'retweet_count': metrics.get('retweet_count', 0),
                    'reply_count': metrics.get('reply_count', 0),
                    'quote_count': metrics.get('quote_count', 0),
                    'bookmark_count': metrics.get('bookmark_count', 0),
                    'topics': topics,
                    'user_verified': getattr(user_data, 'verified', False),
                    'user_followers': getattr(user_data, 'public_metrics', {}).get('followers_count', 0)
                }
            )
            
            self.session.add(raw_content)
            self.session.commit()
            
            # Add to processing queue
            await self._queue_for_processing(raw_content.id)
            
            logger.info(f"Processed tweet {tweet.id} from @{user_data.username}")
            
        except Exception as e:
            logger.error(f"Failed to process tweet {tweet.id}: {e}")
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
                    "source": "twitter"
                })
            )
            
            logger.debug(f"Queued content {content_id} for processing")
            
        except Exception as e:
            logger.error(f"Failed to queue content {content_id}: {e}")
    
    async def search_tweets(self, query: str, max_results: int = 100) -> List[Dict[str, Any]]:
        """Search tweets by query"""
        try:
            tweets = self.client.search_recent_tweets(
                query=f"{query} lang:en OR lang:ru",
                max_results=min(max_results, 100),
                tweet_fields=['created_at', 'public_metrics', 'author_id', 'lang']
            )
            
            if not tweets.data:
                return []
            
            results = []
            for tweet in tweets.data:
                results.append({
                    'id': tweet.id,
                    'text': tweet.text,
                    'created_at': tweet.created_at.isoformat(),
                    'author_id': tweet.author_id,
                    'language': getattr(tweet, 'lang', 'unknown'),
                    'metrics': tweet.public_metrics if hasattr(tweet, 'public_metrics') else {}
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to search tweets: {e}")
            return []
    
    async def get_user_info(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user information"""
        try:
            user = self.client.get_user(
                username=username,
                user_fields=['created_at', 'description', 'public_metrics', 'verified']
            )
            
            if not user.data:
                return None
            
            return {
                'id': user.data.id,
                'username': user.data.username,
                'name': user.data.name,
                'description': getattr(user.data, 'description', ''),
                'verified': getattr(user.data, 'verified', False),
                'created_at': getattr(user.data, 'created_at', ''),
                'public_metrics': getattr(user.data, 'public_metrics', {})
            }
            
        except Exception as e:
            logger.error(f"Failed to get user info for @{username}: {e}")
            return None


# Standalone functions for scheduled tasks
async def run_twitter_ingestion():
    """Run Twitter ingestion service"""
    ingestion = TwitterIngestion()
    try:
        await ingestion.start()
        
        # Schedule periodic collection
        while True:
            await asyncio.sleep(900)  # Check every 15 minutes
            
            # Collect new tweets
            for account in source_config.TWITTER_ACCOUNTS:
                try:
                    await ingestion._collect_user_tweets(account, count=20)
                except Exception as e:
                    logger.error(f"Failed to collect tweets for @{account}: {e}")
            
    except KeyboardInterrupt:
        logger.info("Stopping Twitter ingestion...")
    except Exception as e:
        logger.error(f"Twitter ingestion error: {e}")
    finally:
        await ingestion.stop()


async def search_crypto_trends():
    """Search for trending crypto topics"""
    ingestion = TwitterIngestion()
    try:
        await ingestion.start()
        
        # Search for trending crypto topics
        crypto_queries = [
            "bitcoin price",
            "ethereum news", 
            "crypto regulation",
            "defi hack",
            "nft market",
            "altcoin pump"
        ]
        
        for query in crypto_queries:
            results = await ingestion.search_tweets(query, max_results=50)
            logger.info(f"Found {len(results)} tweets for '{query}'")
            
    except Exception as e:
        logger.error(f"Failed to search crypto trends: {e}")
    finally:
        await ingestion.stop()


if __name__ == "__main__":
    # For testing
    asyncio.run(run_twitter_ingestion())
