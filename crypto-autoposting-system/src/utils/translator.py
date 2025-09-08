"""
Translation service with multiple providers
"""
import logging
import json
import hashlib
from typing import Dict, Optional, List, Any
import deepl
import openai
from langdetect import detect

from ..config import settings, llm_config
from ..utils.redis_client import RedisClient

logger = logging.getLogger(__name__)


class TranslationService:
    """Multi-provider translation service"""
    
    def __init__(self):
        self.redis_client = RedisClient()
        
        # Initialize DeepL
        self.deepl_translator = None
        if settings.deepl_api_key:
            try:
                self.deepl_translator = deepl.Translator(settings.deepl_api_key)
                logger.info("DeepL translator initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize DeepL: {e}")
        
        # Initialize OpenAI
        openai.api_key = settings.openai_api_key
    
    async def translate_with_llm(self, text: str, source_lang: str, target_lang: str = "ru") -> Dict[str, Any]:
        """Translate text using LLM with quality enhancement"""
        try:
            # Create cache key
            cache_key = hashlib.md5(f"{text}:{source_lang}:{target_lang}".encode()).hexdigest()
            cached_result = await self.redis_client.get(f"translation:{cache_key}")
            
            if cached_result:
                return cached_result
            
            # Step 1: Get machine translation
            machine_translation = await self._get_machine_translation(text, source_lang, target_lang)
            
            # Step 2: Enhance with LLM
            enhanced_translation = await self._enhance_translation_with_llm(
                original_text=text,
                machine_translation=machine_translation,
                source_lang=source_lang,
                target_lang=target_lang
            )
            
            result = {
                "original_language": source_lang,
                "machine_translation": machine_translation,
                "human_translation": enhanced_translation.get("human_translation", machine_translation),
                "summary": enhanced_translation.get("summary", ""),
                "glossary": enhanced_translation.get("glossary", []),
                "quality_score": enhanced_translation.get("quality_score", 0.8)
            }
            
            # Cache result for 24 hours
            await self.redis_client.set(f"translation:{cache_key}", result, expire=86400)
            
            return result
            
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            return {
                "original_language": source_lang,
                "machine_translation": text,
                "human_translation": text,
                "summary": "",
                "glossary": [],
                "quality_score": 0.0
            }
    
    async def _get_machine_translation(self, text: str, source_lang: str, target_lang: str) -> str:
        """Get machine translation using available providers"""
        try:
            # Try DeepL first (usually better quality)
            if self.deepl_translator and source_lang != target_lang:
                try:
                    # Map language codes for DeepL
                    deepl_source = self._map_lang_code_for_deepl(source_lang)
                    deepl_target = self._map_lang_code_for_deepl(target_lang)
                    
                    if deepl_source and deepl_target:
                        result = self.deepl_translator.translate_text(
                            text, 
                            source_lang=deepl_source,
                            target_lang=deepl_target
                        )
                        return result.text
                        
                except Exception as e:
                    logger.warning(f"DeepL translation failed: {e}")
            
            # Fallback to Google Translate or other services
            # TODO: Implement Google Translate integration
            
            return text  # Return original if translation fails
            
        except Exception as e:
            logger.error(f"Machine translation failed: {e}")
            return text
    
    def _map_lang_code_for_deepl(self, lang_code: str) -> Optional[str]:
        """Map language codes for DeepL API"""
        mapping = {
            "en": "EN",
            "ru": "RU", 
            "de": "DE",
            "fr": "FR",
            "es": "ES",
            "it": "IT",
            "ja": "JA",
            "ko": "KO",
            "zh": "ZH",
            "pt": "PT",
            "pl": "PL",
            "nl": "NL"
        }
        return mapping.get(lang_code.lower())
    
    async def _enhance_translation_with_llm(
        self, 
        original_text: str, 
        machine_translation: str,
        source_lang: str,
        target_lang: str
    ) -> Dict[str, Any]:
        """Enhance machine translation using LLM"""
        try:
            # Use the translation prompt from config
            prompt = llm_config.PROMPTS["translation"].format(lang=source_lang)
            
            user_message = f"""
Оригинальный текст ({source_lang}): {original_text}

Машинный перевод: {machine_translation}

Пожалуйста, улучши перевод согласно инструкциям.
            """
            
            response = await self._call_openai(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_message}
                ],
                model=llm_config.OPENAI_MODELS["translation"],
                temperature=0.3
            )
            
            if not response:
                return {"human_translation": machine_translation}
            
            # Try to parse as JSON
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                # If not JSON, treat as enhanced translation
                return {
                    "human_translation": response,
                    "summary": "",
                    "glossary": []
                }
                
        except Exception as e:
            logger.error(f"LLM translation enhancement failed: {e}")
            return {"human_translation": machine_translation}
    
    async def detect_language(self, text: str) -> str:
        """Detect language of text"""
        try:
            return detect(text)
        except Exception as e:
            logger.warning(f"Language detection failed: {e}")
            return "unknown"
    
    async def translate_batch(self, texts: List[str], source_lang: str, target_lang: str = "ru") -> List[Dict[str, Any]]:
        """Translate multiple texts in batch"""
        results = []
        
        for text in texts:
            try:
                result = await self.translate_with_llm(text, source_lang, target_lang)
                results.append(result)
            except Exception as e:
                logger.error(f"Batch translation failed for text: {e}")
                results.append({
                    "original_language": source_lang,
                    "machine_translation": text,
                    "human_translation": text,
                    "summary": "",
                    "glossary": [],
                    "quality_score": 0.0
                })
        
        return results
    
    async def get_translation_quality_score(self, original: str, translation: str) -> float:
        """Assess translation quality using LLM"""
        try:
            prompt = """
Оцени качество перевода от 0.0 до 1.0, где:
1.0 - отличный перевод, полностью передает смысл
0.8 - хороший перевод с незначительными неточностями  
0.6 - приемлемый перевод с некоторыми ошибками
0.4 - плохой перевод с серьезными ошибками
0.2 - очень плохой перевод
0.0 - перевод не передает смысл

Верни только число от 0.0 до 1.0.
            """
            
            user_message = f"""
Оригинал: {original}
Перевод: {translation}
            """
            
            response = await self._call_openai(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_message}
                ],
                model="gpt-3.5-turbo",
                temperature=0.1
            )
            
            if response:
                try:
                    score = float(response.strip())
                    return max(0.0, min(1.0, score))
                except ValueError:
                    pass
            
            return 0.8  # Default score
            
        except Exception as e:
            logger.error(f"Quality scoring failed: {e}")
            return 0.8
    
    async def extract_key_terms(self, text: str, language: str = "ru") -> List[Dict[str, str]]:
        """Extract key terms and their explanations"""
        try:
            prompt = f"""
Извлеки из текста 3-5 ключевых криптовалютных терминов и дай им краткие объяснения на русском языке.
Верни результат в формате JSON:
{{"terms": [{{"term": "термин", "explanation": "объяснение"}}]}}
            """
            
            response = await self._call_openai(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text}
                ],
                model="gpt-3.5-turbo",
                temperature=0.3
            )
            
            if response:
                try:
                    result = json.loads(response)
                    return result.get("terms", [])
                except json.JSONDecodeError:
                    pass
            
            return []
            
        except Exception as e:
            logger.error(f"Term extraction failed: {e}")
            return []
    
    async def _call_openai(self, messages: List[Dict], model: str, temperature: float = 0.5) -> Optional[str]:
        """Call OpenAI API with error handling"""
        try:
            response = await openai.ChatCompletion.acreate(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=1000
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            return None
    
    async def get_supported_languages(self) -> List[str]:
        """Get list of supported languages"""
        supported = ["en", "ru", "de", "fr", "es", "it", "ja", "ko", "zh", "pt"]
        
        if self.deepl_translator:
            try:
                # Get DeepL supported languages
                deepl_languages = self.deepl_translator.get_source_languages()
                deepl_codes = [lang.code.lower() for lang in deepl_languages]
                supported.extend(deepl_codes)
            except Exception as e:
                logger.warning(f"Failed to get DeepL languages: {e}")
        
        return list(set(supported))


# Standalone functions
async def translate_text(text: str, source_lang: str, target_lang: str = "ru") -> Dict[str, Any]:
    """Standalone function to translate text"""
    service = TranslationService()
    return await service.translate_with_llm(text, source_lang, target_lang)


async def detect_and_translate(text: str, target_lang: str = "ru") -> Dict[str, Any]:
    """Detect language and translate text"""
    service = TranslationService()
    
    # Detect language first
    source_lang = await service.detect_language(text)
    
    # Skip translation if already in target language
    if source_lang == target_lang:
        return {
            "original_language": source_lang,
            "machine_translation": text,
            "human_translation": text,
            "summary": "",
            "glossary": [],
            "quality_score": 1.0
        }
    
    # Translate
    return await service.translate_with_llm(text, source_lang, target_lang)


if __name__ == "__main__":
    # Test translation service
    import asyncio
    
    async def test():
        service = TranslationService()
        
        test_text = "Bitcoin price reached a new all-time high today as institutional investors continue to show strong interest in cryptocurrency markets."
        
        result = await service.translate_with_llm(test_text, "en", "ru")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test())
