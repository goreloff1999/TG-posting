"""
Redis client utility for caching and queues
"""
import redis
import json
import logging
from typing import Any, Optional, List, Dict
import pickle

from ..config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client wrapper"""
    
    def __init__(self):
        self.redis = None
        self._connect()
    
    def _connect(self):
        """Connect to Redis"""
        try:
            self.redis = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            
            # Test connection
            self.redis.ping()
            logger.info("Redis client connected successfully")
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """Set a value in Redis"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            
            result = self.redis.set(key, value, ex=expire)
            return bool(result)
            
        except Exception as e:
            logger.error(f"Failed to set Redis key {key}: {e}")
            return False
    
    async def get(self, key: str) -> Optional[Any]:
        """Get a value from Redis"""
        try:
            value = self.redis.get(key)
            if value is None:
                return None
            
            # Try to parse as JSON
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
                
        except Exception as e:
            logger.error(f"Failed to get Redis key {key}: {e}")
            return None
    
    async def delete(self, key: str) -> bool:
        """Delete a key from Redis"""
        try:
            result = self.redis.delete(key)
            return bool(result)
            
        except Exception as e:
            logger.error(f"Failed to delete Redis key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis"""
        try:
            return bool(self.redis.exists(key))
        except Exception as e:
            logger.error(f"Failed to check Redis key {key}: {e}")
            return False
    
    # Queue operations
    async def lpush(self, queue: str, item: Any) -> bool:
        """Add item to left of queue"""
        try:
            if isinstance(item, (dict, list)):
                item = json.dumps(item)
            
            result = self.redis.lpush(queue, item)
            return bool(result)
            
        except Exception as e:
            logger.error(f"Failed to lpush to queue {queue}: {e}")
            return False
    
    async def rpop(self, queue: str) -> Optional[Any]:
        """Remove and return item from right of queue"""
        try:
            value = self.redis.rpop(queue)
            if value is None:
                return None
            
            # Try to parse as JSON
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
                
        except Exception as e:
            logger.error(f"Failed to rpop from queue {queue}: {e}")
            return None
    
    async def brpop(self, queue: str, timeout: int = 0) -> Optional[Any]:
        """Blocking pop from queue"""
        try:
            result = self.redis.brpop(queue, timeout=timeout)
            if result is None:
                return None
            
            _, value = result
            
            # Try to parse as JSON
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
                
        except Exception as e:
            logger.error(f"Failed to brpop from queue {queue}: {e}")
            return None
    
    async def llen(self, queue: str) -> int:
        """Get queue length"""
        try:
            return self.redis.llen(queue)
        except Exception as e:
            logger.error(f"Failed to get length of queue {queue}: {e}")
            return 0
    
    # Hash operations
    async def hset(self, name: str, mapping: Dict[str, Any]) -> bool:
        """Set hash fields"""
        try:
            # Convert values to strings/JSON
            string_mapping = {}
            for key, value in mapping.items():
                if isinstance(value, (dict, list)):
                    string_mapping[key] = json.dumps(value)
                else:
                    string_mapping[key] = str(value)
            
            result = self.redis.hset(name, mapping=string_mapping)
            return bool(result)
            
        except Exception as e:
            logger.error(f"Failed to hset {name}: {e}")
            return False
    
    async def hget(self, name: str, key: str) -> Optional[Any]:
        """Get hash field value"""
        try:
            value = self.redis.hget(name, key)
            if value is None:
                return None
            
            # Try to parse as JSON
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
                
        except Exception as e:
            logger.error(f"Failed to hget {name}.{key}: {e}")
            return None
    
    async def hgetall(self, name: str) -> Dict[str, Any]:
        """Get all hash fields"""
        try:
            data = self.redis.hgetall(name)
            
            # Try to parse JSON values
            result = {}
            for key, value in data.items():
                try:
                    result[key] = json.loads(value)
                except json.JSONDecodeError:
                    result[key] = value
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to hgetall {name}: {e}")
            return {}
    
    # Set operations
    async def sadd(self, name: str, *values: Any) -> bool:
        """Add values to set"""
        try:
            string_values = []
            for value in values:
                if isinstance(value, (dict, list)):
                    string_values.append(json.dumps(value))
                else:
                    string_values.append(str(value))
            
            result = self.redis.sadd(name, *string_values)
            return bool(result)
            
        except Exception as e:
            logger.error(f"Failed to sadd to {name}: {e}")
            return False
    
    async def sismember(self, name: str, value: Any) -> bool:
        """Check if value is in set"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            else:
                value = str(value)
            
            return bool(self.redis.sismember(name, value))
            
        except Exception as e:
            logger.error(f"Failed to check sismember {name}: {e}")
            return False
    
    async def smembers(self, name: str) -> List[Any]:
        """Get all set members"""
        try:
            members = self.redis.smembers(name)
            
            # Try to parse JSON values
            result = []
            for member in members:
                try:
                    result.append(json.loads(member))
                except json.JSONDecodeError:
                    result.append(member)
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get smembers {name}: {e}")
            return []
    
    # Caching helpers
    async def cache_content_similarity(self, content_id: str, similarity_data: Dict[str, Any], expire: int = 3600):
        """Cache content similarity data"""
        key = f"similarity:{content_id}"
        await self.set(key, similarity_data, expire=expire)
    
    async def get_cached_similarity(self, content_id: str) -> Optional[Dict[str, Any]]:
        """Get cached similarity data"""
        key = f"similarity:{content_id}"
        return await self.get(key)
    
    async def cache_llm_response(self, prompt_hash: str, response: Dict[str, Any], expire: int = 7200):
        """Cache LLM response"""
        key = f"llm_cache:{prompt_hash}"
        await self.set(key, response, expire=expire)
    
    async def get_cached_llm_response(self, prompt_hash: str) -> Optional[Dict[str, Any]]:
        """Get cached LLM response"""
        key = f"llm_cache:{prompt_hash}"
        return await self.get(key)
    
    async def rate_limit_check(self, key: str, limit: int, window: int) -> bool:
        """Check rate limit using sliding window"""
        try:
            current = self.redis.incr(key)
            if current == 1:
                self.redis.expire(key, window)
            
            return current <= limit
            
        except Exception as e:
            logger.error(f"Failed to check rate limit for {key}: {e}")
            return True  # Allow if check fails
    
    def close(self):
        """Close Redis connection"""
        try:
            if self.redis:
                self.redis.close()
                logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")


# Global Redis client instance
redis_client = RedisClient()
