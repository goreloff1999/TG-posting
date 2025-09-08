"""
Content similarity checking using embeddings
"""
import logging
import json
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import openai

from ..config import settings, llm_config
from ..models import SessionLocal, ContentArchive
from ..utils.redis_client import RedisClient

logger = logging.getLogger(__name__)


class SimilarityChecker:
    """Content similarity checker using embeddings"""
    
    def __init__(self):
        self.session = SessionLocal()
        self.redis_client = RedisClient()
        
        # Initialize embedding model
        try:
            self.embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            logger.info("Sentence transformer model loaded")
        except Exception as e:
            logger.warning(f"Failed to load sentence transformer: {e}")
            self.embedding_model = None
        
        # OpenAI for embeddings as fallback
        openai.api_key = settings.openai_api_key
    
    async def check_similarity(self, text: str, content_id: str) -> Dict[str, Any]:
        """Check similarity of text against existing content"""
        try:
            # Check cache first
            cached_result = await self.redis_client.get_cached_similarity(content_id)
            if cached_result:
                return cached_result
            
            # Get embedding for the text
            embedding = await self._get_embedding(text)
            if embedding is None:
                logger.warning("Failed to get embedding")
                return self._default_similarity_result()
            
            # Find similar content
            similar_content = await self._find_similar_content(embedding, text)
            
            # Calculate overall similarity score
            max_similarity = 0.0
            if similar_content:
                max_similarity = max(item["similarity"] for item in similar_content)
            
            result = {
                "similarity_score": max_similarity,
                "similar_content_ids": [item["content_id"] for item in similar_content],
                "similar_content_details": similar_content,
                "is_duplicate": max_similarity > settings.min_similarity_threshold,
                "embedding": embedding.tolist() if isinstance(embedding, np.ndarray) else embedding
            }
            
            # Cache result
            await self.redis_client.cache_content_similarity(content_id, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Similarity check failed: {e}")
            return self._default_similarity_result()
    
    async def _get_embedding(self, text: str) -> Optional[np.ndarray]:
        """Get embedding for text"""
        try:
            # Try local model first
            if self.embedding_model:
                embedding = self.embedding_model.encode([text])
                return embedding[0]
            
            # Fallback to OpenAI
            response = await openai.Embedding.acreate(
                model=llm_config.OPENAI_MODELS["similarity"],
                input=text
            )
            
            return np.array(response.data[0].embedding)
            
        except Exception as e:
            logger.error(f"Failed to get embedding: {e}")
            return None
    
    async def _find_similar_content(self, embedding: np.ndarray, text: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Find similar content from archive"""
        try:
            # Get content from archive with embeddings
            archive_entries = self.session.query(ContentArchive).filter(
                ContentArchive.content_embedding.isnot(None)
            ).limit(1000).all()  # Limit for performance
            
            if not archive_entries:
                return []
            
            similar_items = []
            
            for entry in archive_entries:
                try:
                    # Parse stored embedding
                    stored_embedding = np.array(entry.content_embedding)
                    
                    # Calculate cosine similarity
                    similarity = cosine_similarity(
                        embedding.reshape(1, -1),
                        stored_embedding.reshape(1, -1)
                    )[0][0]
                    
                    # Include if similarity is above threshold
                    if similarity > 0.3:  # Lower threshold for finding candidates
                        similar_items.append({
                            "content_id": str(entry.processed_content_id),
                            "similarity": float(similarity),
                            "title": entry.title,
                            "published_at": entry.published_at.isoformat() if entry.published_at else "",
                            "platform": entry.platform,
                            "engagement_score": entry.engagement_score or 0.0,
                            "snippet": entry.content_text[:200] + "..." if len(entry.content_text) > 200 else entry.content_text
                        })
                        
                except Exception as e:
                    logger.warning(f"Failed to process archive entry {entry.id}: {e}")
                    continue
            
            # Sort by similarity and return top results
            similar_items.sort(key=lambda x: x["similarity"], reverse=True)
            return similar_items[:limit]
            
        except Exception as e:
            logger.error(f"Failed to find similar content: {e}")
            return []
    
    async def add_to_archive(self, processed_content_id: str, title: str, content_text: str, 
                           platform: str = "telegram") -> bool:
        """Add content to similarity archive"""
        try:
            # Get embedding for content
            embedding = await self._get_embedding(content_text)
            if embedding is None:
                logger.warning(f"Failed to get embedding for archival content {processed_content_id}")
                return False
            
            # Extract entities and topics
            entities = await self._extract_entities(content_text)
            topics = await self._extract_topics(content_text)
            
            # Create archive entry
            archive_entry = ContentArchive(
                processed_content_id=processed_content_id,
                title=title,
                content_text=content_text,
                content_embedding=embedding.tolist() if isinstance(embedding, np.ndarray) else embedding,
                entities=entities,
                topics=topics,
                published_at=datetime.utcnow(),
                platform=platform,
                engagement_score=0.0
            )
            
            self.session.add(archive_entry)
            self.session.commit()
            
            logger.info(f"Added content {processed_content_id} to similarity archive")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add content to archive: {e}")
            self.session.rollback()
            return False
    
    async def _extract_entities(self, text: str) -> List[str]:
        """Extract named entities from text"""
        try:
            # Simple keyword-based entity extraction for crypto
            crypto_entities = []
            
            # Common crypto entities
            crypto_keywords = [
                "bitcoin", "btc", "ethereum", "eth", "binance", "coinbase",
                "tether", "usdt", "cardano", "ada", "solana", "sol",
                "polygon", "matic", "chainlink", "link", "litecoin", "ltc",
                "dogecoin", "doge", "shiba", "avalanche", "avax"
            ]
            
            text_lower = text.lower()
            for keyword in crypto_keywords:
                if keyword in text_lower:
                    crypto_entities.append(keyword)
            
            # Extract potential project names (capitalized words)
            import re
            potential_entities = re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)*\b', text)
            crypto_entities.extend(potential_entities[:5])  # Limit to 5
            
            return list(set(crypto_entities))  # Remove duplicates
            
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return []
    
    async def _extract_topics(self, text: str) -> List[str]:
        """Extract topic tags from text"""
        try:
            topics = []
            text_lower = text.lower()
            
            # Topic mapping
            topic_keywords = {
                "price": ["price", "cost", "value", "expensive", "cheap", "pump", "dump"],
                "trading": ["trading", "trade", "buy", "sell", "exchange", "market"],
                "technology": ["technology", "tech", "blockchain", "protocol", "network"],
                "regulation": ["regulation", "legal", "law", "government", "sec", "compliance"],
                "defi": ["defi", "decentralized", "yield", "farming", "liquidity", "pool"],
                "nft": ["nft", "non-fungible", "collectible", "art", "opensea"],
                "security": ["hack", "security", "exploit", "vulnerability", "attack"],
                "partnership": ["partnership", "collaboration", "integration", "alliance"],
                "development": ["development", "update", "upgrade", "release", "launch"]
            }
            
            for topic, keywords in topic_keywords.items():
                if any(keyword in text_lower for keyword in keywords):
                    topics.append(topic)
            
            return topics
            
        except Exception as e:
            logger.error(f"Topic extraction failed: {e}")
            return []
    
    def _default_similarity_result(self) -> Dict[str, Any]:
        """Return default similarity result when check fails"""
        return {
            "similarity_score": 0.0,
            "similar_content_ids": [],
            "similar_content_details": [],
            "is_duplicate": False,
            "embedding": None
        }
    
    async def update_engagement_score(self, content_id: str, engagement_data: Dict[str, Any]):
        """Update engagement score for archived content"""
        try:
            archive_entry = self.session.query(ContentArchive).filter(
                ContentArchive.processed_content_id == content_id
            ).first()
            
            if archive_entry:
                # Calculate engagement score based on metrics
                views = engagement_data.get("views", 0)
                likes = engagement_data.get("likes", 0)
                shares = engagement_data.get("shares", 0)
                comments = engagement_data.get("comments", 0)
                
                # Simple engagement scoring
                engagement_score = (likes * 2 + shares * 3 + comments * 2) / max(views, 1)
                archive_entry.engagement_score = engagement_score
                
                self.session.commit()
                logger.info(f"Updated engagement score for {content_id}: {engagement_score}")
            
        except Exception as e:
            logger.error(f"Failed to update engagement score: {e}")
            self.session.rollback()
    
    async def find_trending_topics(self, days: int = 7) -> List[Dict[str, Any]]:
        """Find trending topics based on recent content"""
        try:
            from datetime import datetime, timedelta
            
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Get recent content
            recent_content = self.session.query(ContentArchive).filter(
                ContentArchive.published_at >= cutoff_date
            ).all()
            
            # Count topic occurrences
            topic_counts = {}
            for content in recent_content:
                for topic in content.topics:
                    if topic not in topic_counts:
                        topic_counts[topic] = {"count": 0, "avg_engagement": 0.0, "contents": []}
                    
                    topic_counts[topic]["count"] += 1
                    topic_counts[topic]["avg_engagement"] += content.engagement_score or 0.0
                    topic_counts[topic]["contents"].append(content.id)
            
            # Calculate average engagement and sort
            trending_topics = []
            for topic, data in topic_counts.items():
                avg_engagement = data["avg_engagement"] / data["count"] if data["count"] > 0 else 0.0
                trending_topics.append({
                    "topic": topic,
                    "count": data["count"],
                    "avg_engagement": avg_engagement,
                    "trend_score": data["count"] * avg_engagement
                })
            
            trending_topics.sort(key=lambda x: x["trend_score"], reverse=True)
            return trending_topics[:10]
            
        except Exception as e:
            logger.error(f"Failed to find trending topics: {e}")
            return []
    
    def close(self):
        """Close database connection"""
        self.session.close()


# Helper functions
async def archive_published_content(processed_content_id: str, title: str, content_text: str, platform: str = "telegram"):
    """Archive published content for similarity checking"""
    checker = SimilarityChecker()
    try:
        return await checker.add_to_archive(processed_content_id, title, content_text, platform)
    finally:
        checker.close()


async def check_content_similarity(text: str, content_id: str) -> Dict[str, Any]:
    """Standalone function to check content similarity"""
    checker = SimilarityChecker()
    try:
        return await checker.check_similarity(text, content_id)
    finally:
        checker.close()


if __name__ == "__main__":
    # Test similarity checker
    import asyncio
    
    async def test():
        checker = SimilarityChecker()
        try:
            result = await checker.check_similarity("Bitcoin price reaches new high", "test-123")
            print(json.dumps(result, indent=2))
        finally:
            checker.close()
    
    asyncio.run(test())
