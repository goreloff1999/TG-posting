"""
Content processing pipeline with LLM integration
"""
import logging
import asyncio
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import openai
from langdetect import detect
import re

from ..config import settings, llm_config
from ..models import SessionLocal, RawContent, ProcessedContent, ContentStatus, Priority
from ..utils.redis_client import RedisClient
from ..utils.similarity import SimilarityChecker
from ..utils.translator import TranslationService

logger = logging.getLogger(__name__)


class ContentProcessor:
    """Main content processing pipeline"""
    
    def __init__(self):
        self.session = SessionLocal()
        self.redis_client = RedisClient()
        self.similarity_checker = SimilarityChecker()
        self.translator = TranslationService()
        
        # Initialize OpenAI
        openai.api_key = settings.openai_api_key
        
    async def process_content_queue(self):
        """Process content from queue continuously"""
        try:
            while True:
                # Get next item from queue
                queue_item = await self.redis_client.brpop("content_processing_queue", timeout=30)
                
                if queue_item:
                    try:
                        content_id = queue_item["content_id"]
                        await self.process_single_content(content_id)
                    except Exception as e:
                        logger.error(f"Failed to process content {queue_item}: {e}")
                
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Content processing queue error: {e}")
    
    async def process_single_content(self, content_id: str):
        """Process a single piece of content through the full pipeline"""
        try:
            # Get raw content
            raw_content = self.session.query(RawContent).filter(
                RawContent.id == content_id
            ).first()
            
            if not raw_content:
                logger.warning(f"Raw content {content_id} not found")
                return
            
            if raw_content.processed:
                logger.info(f"Content {content_id} already processed")
                return
            
            logger.info(f"Processing content {content_id}")
            
            # Step 1: Initial analysis
            analysis_result = await self._analyze_content(raw_content)
            if not analysis_result:
                logger.warning(f"Failed to analyze content {content_id}")
                return
            
            # Step 2: Translation if needed
            translation_result = await self._translate_content(raw_content, analysis_result)
            
            # Step 3: Similarity check
            similarity_result = await self._check_similarity(raw_content, translation_result)
            
            # Step 4: Paraphrasing and humanization
            paraphrase_result = await self._paraphrase_content(
                raw_content, translation_result, similarity_result, analysis_result
            )
            
            # Step 5: Create processed content record
            processed_content = await self._create_processed_content(
                raw_content, analysis_result, translation_result, 
                similarity_result, paraphrase_result
            )
            
            # Step 6: Determine if HITL is needed
            requires_hitl = await self._check_hitl_requirements(processed_content, analysis_result)
            processed_content.requires_hitl = requires_hitl
            
            # Update status
            if requires_hitl:
                processed_content.status = ContentStatus.PENDING.value
            else:
                processed_content.status = ContentStatus.READY.value
            
            # Mark raw content as processed
            raw_content.processed = True
            
            self.session.commit()
            
            # Queue for publishing if ready
            if not requires_hitl:
                await self._queue_for_publishing(processed_content.id)
            
            logger.info(f"Successfully processed content {content_id}")
            
        except Exception as e:
            logger.error(f"Failed to process content {content_id}: {e}")
            self.session.rollback()
    
    async def _analyze_content(self, raw_content: RawContent) -> Optional[Dict[str, Any]]:
        """Analyze content using LLM"""
        try:
            # Create prompt hash for caching
            prompt_data = {
                "text": raw_content.text,
                "source": raw_content.source.username,
                "template": "analysis"
            }
            prompt_hash = hashlib.md5(json.dumps(prompt_data, sort_keys=True).encode()).hexdigest()
            
            # Check cache first
            cached_result = await self.redis_client.get_cached_llm_response(prompt_hash)
            if cached_result:
                return cached_result
            
            # Prepare prompt
            prompt = llm_config.PROMPTS["analysis"].format(
                source_name=raw_content.source.username,
                source_url="",  # TODO: Add source URL if available
                lang=raw_content.language or "unknown",
                raw_text=raw_content.text
            )
            
            # Call OpenAI
            response = await self._call_openai(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": raw_content.text}
                ],
                model=llm_config.OPENAI_MODELS["analysis"],
                temperature=0.3
            )
            
            if not response:
                return None
            
            # Parse JSON response
            try:
                result = json.loads(response)
                
                # Validate required fields
                required_fields = ["summary_2", "key_points", "risk_tags", "priority", "language"]
                if not all(field in result for field in required_fields):
                    logger.warning(f"LLM analysis missing required fields: {result}")
                    return None
                
                # Cache result
                await self.redis_client.cache_llm_response(prompt_hash, result)
                
                return result
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM analysis response: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Content analysis failed: {e}")
            return None
    
    async def _translate_content(self, raw_content: RawContent, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Translate content if needed"""
        try:
            detected_lang = analysis.get("language", raw_content.language)
            
            # Skip translation if already in Russian
            if detected_lang in ["ru", "russian"]:
                return {
                    "original_language": detected_lang,
                    "translated_text": raw_content.text,
                    "human_translation": raw_content.text,
                    "summary": analysis.get("summary_2", ""),
                    "glossary": []
                }
            
            # Use translation service
            translation_result = await self.translator.translate_with_llm(
                text=raw_content.text,
                source_lang=detected_lang,
                target_lang="ru"
            )
            
            return translation_result
            
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            return {
                "original_language": raw_content.language or "unknown",
                "translated_text": raw_content.text,
                "human_translation": raw_content.text,
                "summary": "",
                "glossary": []
            }
    
    async def _check_similarity(self, raw_content: RawContent, translation: Dict[str, Any]) -> Dict[str, Any]:
        """Check similarity with existing content"""
        try:
            # Use translated/original text for similarity check
            text_to_check = translation.get("human_translation", raw_content.text)
            
            similarity_result = await self.similarity_checker.check_similarity(
                text=text_to_check,
                content_id=str(raw_content.id)
            )
            
            return similarity_result
            
        except Exception as e:
            logger.error(f"Similarity check failed: {e}")
            return {
                "similarity_score": 0.0,
                "similar_content_ids": [],
                "is_duplicate": False
            }
    
    async def _paraphrase_content(
        self, 
        raw_content: RawContent, 
        translation: Dict[str, Any], 
        similarity: Dict[str, Any],
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Paraphrase content for uniqueness and human-like style"""
        try:
            # Prepare context for paraphrasing
            related_articles = []
            if similarity.get("similar_content_ids"):
                # TODO: Fetch related articles from database
                pass
            
            # Create prompt hash for caching
            prompt_data = {
                "text": translation.get("human_translation", ""),
                "summary": translation.get("summary", ""),
                "similarity_score": similarity.get("similarity_score", 0),
                "template": "paraphrase"
            }
            prompt_hash = hashlib.md5(json.dumps(prompt_data, sort_keys=True).encode()).hexdigest()
            
            # Check cache
            cached_result = await self.redis_client.get_cached_llm_response(prompt_hash)
            if cached_result:
                return cached_result
            
            # Prepare prompt with context
            prompt = llm_config.PROMPTS["paraphrase"].format(
                threshold=settings.min_similarity_threshold
            )
            
            user_message = f"""
Исходный текст (перевод): {translation.get("human_translation", "")}

Краткий пересказ: {translation.get("summary", "")}

Схожесть с архивом: {similarity.get("similarity_score", 0):.2f}

{f"Связанные статьи: {related_articles}" if related_articles else ""}

Пожалуйста, создай уникальную статью согласно инструкциям.
            """
            
            # Call OpenAI
            response = await self._call_openai(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_message}
                ],
                model=llm_config.OPENAI_MODELS["paraphrase"],
                temperature=0.7
            )
            
            if not response:
                return {}
            
            # Parse response
            try:
                result = json.loads(response)
                
                # Cache result
                await self.redis_client.cache_llm_response(prompt_hash, result)
                
                return result
                
            except json.JSONDecodeError:
                # If not JSON, treat as plain text
                return {
                    "headline_short": "",
                    "headline_long": "",
                    "body": response,
                    "author_note": "",
                    "tags": [],
                    "plagiarism_check_hint": ""
                }
                
        except Exception as e:
            logger.error(f"Paraphrasing failed: {e}")
            return {}
    
    async def _create_processed_content(
        self,
        raw_content: RawContent,
        analysis: Dict[str, Any],
        translation: Dict[str, Any],
        similarity: Dict[str, Any],
        paraphrase: Dict[str, Any]
    ) -> ProcessedContent:
        """Create processed content record"""
        try:
            processed = ProcessedContent(
                raw_content_id=raw_content.id,
                
                # Analysis results
                summary=analysis.get("summary_2", ""),
                key_points=analysis.get("key_points", []),
                content_type=self._classify_content_type(analysis, raw_content.text),
                priority=analysis.get("priority", Priority.MEDIUM.value),
                risk_level=self._calculate_risk_level(analysis),
                risk_tags=analysis.get("risk_tags", []),
                
                # Translation
                original_language=translation.get("original_language", "unknown"),
                translated_text=translation.get("human_translation", raw_content.text),
                translation_quality_score=0.8,  # TODO: Implement quality scoring
                
                # Paraphrasing
                paraphrased_text=paraphrase.get("body", ""),
                headline_short=paraphrase.get("headline_short", ""),
                headline_long=paraphrase.get("headline_long", ""),
                author_note=paraphrase.get("author_note", ""),
                tags=paraphrase.get("tags", []),
                
                # Similarity
                similarity_score=similarity.get("similarity_score", 0.0),
                similar_content_ids=similarity.get("similar_content_ids", []),
                
                # Metadata
                processing_metadata={
                    "analysis": analysis,
                    "translation": translation,
                    "similarity": similarity,
                    "paraphrase": paraphrase,
                    "processed_at": datetime.utcnow().isoformat()
                }
            )
            
            self.session.add(processed)
            self.session.flush()  # Get ID
            
            return processed
            
        except Exception as e:
            logger.error(f"Failed to create processed content: {e}")
            raise
    
    def _classify_content_type(self, analysis: Dict[str, Any], text: str) -> str:
        """Classify content type based on analysis and text"""
        risk_tags = analysis.get("risk_tags", [])
        
        if "hack" in risk_tags:
            return "hack"
        elif "regulation" in risk_tags:
            return "regulatory"
        elif "rumor" in risk_tags:
            return "leak"
        elif any(word in text.lower() for word in ["analysis", "technical", "whitepaper"]):
            return "technical"
        elif any(word in text.lower() for word in ["price", "market", "trading"]):
            return "analysis"
        else:
            return "news"
    
    def _calculate_risk_level(self, analysis: Dict[str, Any]) -> str:
        """Calculate overall risk level"""
        risk_tags = analysis.get("risk_tags", [])
        
        if any(tag in risk_tags for tag in ["hack", "scam", "exploit"]):
            return "high"
        elif any(tag in risk_tags for tag in ["rumor", "regulation"]):
            return "medium"
        else:
            return "low"
    
    async def _check_hitl_requirements(self, processed: ProcessedContent, analysis: Dict[str, Any]) -> bool:
        """Determine if human-in-the-loop review is required"""
        try:
            # High risk content always requires HITL
            if processed.risk_level == "high":
                return True
            
            # High similarity requires review
            if processed.similarity_score > settings.min_similarity_threshold:
                return True
            
            # Sensitive topics require review
            sensitive_keywords = ["hack", "scam", "regulation", "sec", "lawsuit"]
            if any(keyword in processed.translated_text.lower() for keyword in sensitive_keywords):
                return True
            
            # Check quality of paraphrased content
            if not processed.paraphrased_text or len(processed.paraphrased_text) < 100:
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"HITL check failed: {e}")
            return True  # Default to requiring review
    
    async def _queue_for_publishing(self, content_id: str):
        """Queue content for publishing"""
        try:
            await self.redis_client.lpush(
                "content_publishing_queue",
                json.dumps({
                    "content_id": str(content_id),
                    "timestamp": datetime.utcnow().isoformat()
                })
            )
            
            logger.info(f"Queued content {content_id} for publishing")
            
        except Exception as e:
            logger.error(f"Failed to queue content {content_id} for publishing: {e}")
    
    async def _call_openai(self, messages: List[Dict], model: str, temperature: float = 0.5) -> Optional[str]:
        """Call OpenAI API with error handling and retries"""
        try:
            response = await openai.ChatCompletion.acreate(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=1500
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            return None
    
    def close(self):
        """Close connections"""
        self.session.close()


# Standalone function for running processor
async def run_content_processor():
    """Run content processor continuously"""
    processor = ContentProcessor()
    try:
        await processor.process_content_queue()
    except KeyboardInterrupt:
        logger.info("Stopping content processor...")
    except Exception as e:
        logger.error(f"Content processor error: {e}")
    finally:
        processor.close()


if __name__ == "__main__":
    asyncio.run(run_content_processor())
