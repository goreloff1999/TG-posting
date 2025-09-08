"""
Configuration module for crypto autoposting system
"""
import os
from typing import List, Dict, Any
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """Application settings"""
    
    # Debug & Logging
    debug: bool = Field(default=False, env="DEBUG")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    # Database
    database_url: str = Field(..., env="DATABASE_URL")
    redis_url: str = Field(..., env="REDIS_URL")
    elasticsearch_url: str = Field(..., env="ELASTICSEARCH_URL")
    
    # API Keys
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    deepl_api_key: str = Field(..., env="DEEPL_API_KEY")
    google_translate_api_key: str = Field(default="", env="GOOGLE_TRANSLATE_API_KEY")
    
    # Telegram
    telegram_api_id: int = Field(..., env="TELEGRAM_API_ID")
    telegram_api_hash: str = Field(..., env="TELEGRAM_API_HASH")
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    telegram_channel_id: str = Field(..., env="TELEGRAM_CHANNEL_ID")
    
    # Twitter/X
    twitter_api_key: str = Field(default="", env="TWITTER_API_KEY")
    twitter_api_secret: str = Field(default="", env="TWITTER_API_SECRET")
    twitter_access_token: str = Field(default="", env="TWITTER_ACCESS_TOKEN")
    twitter_access_token_secret: str = Field(default="", env="TWITTER_ACCESS_TOKEN_SECRET")
    
    # Image Generation
    stability_api_key: str = Field(default="", env="STABILITY_API_KEY")
    midjourney_api_key: str = Field(default="", env="MIDJOURNEY_API_KEY")
    
    # Content Settings
    min_similarity_threshold: float = Field(default=0.7, env="MIN_SIMILARITY_THRESHOLD")
    max_posts_per_day: int = Field(default=10, env="MAX_POSTS_PER_DAY")
    affiliate_link_frequency: int = Field(default=5, env="AFFILIATE_LINK_FREQUENCY")
    hitl_risk_threshold: str = Field(default="high", env="HITL_RISK_THRESHOLD")
    
    # S3/MinIO Storage
    s3_endpoint: str = Field(..., env="S3_ENDPOINT")
    s3_access_key: str = Field(..., env="S3_ACCESS_KEY")
    s3_secret_key: str = Field(..., env="S3_SECRET_KEY")
    s3_bucket: str = Field(default="crypto-content", env="S3_BUCKET")
    
    # Monitoring
    prometheus_port: int = Field(default=9090, env="PROMETHEUS_PORT")
    grafana_port: int = Field(default=3000, env="GRAFANA_PORT")
    
    class Config:
        env_file = ".env"
        case_sensitive = False


class SourceConfig:
    """Configuration for content sources"""
    
    TELEGRAM_CHANNELS = [
        "@Cointelegraph",
        "@CoinDesk",
        "@TheBlock__",
        "@CryptoSlate",
        "@binance",
        "@ethereum",
        "@bitcoin"
    ]
    
    TWITTER_ACCOUNTS = [
        "cz_binance",
        "coinbureau", 
        "whale_alert",
        "ethereum",
        "bitcoin",
        "VitalikButerin"
    ]
    
    SOURCE_WEIGHTS = {
        # Telegram channels weights
        "@Cointelegraph": 0.9,
        "@CoinDesk": 0.9,
        "@TheBlock__": 0.8,
        "@CryptoSlate": 0.7,
        "@binance": 0.8,
        
        # Twitter accounts weights
        "cz_binance": 0.9,
        "coinbureau": 0.8,
        "whale_alert": 0.7,
        "VitalikButerin": 0.9
    }


class LLMConfig:
    """LLM and AI configuration"""
    
    OPENAI_MODELS = {
        "analysis": "gpt-4",
        "translation": "gpt-4",
        "paraphrase": "gpt-4",
        "similarity": "text-embedding-ada-002"
    }
    
    PROMPTS = {
        "analysis": """
System: Ты — скрипт-помощник для первичной обработки найденного текста о крипте.
User input variables: {{source_name}}, {{source_url}}, {{lang}}, {{raw_text}}.
Task: Верни JSON с полями: summary_2 (2-sentence summary), key_points (3 items), risk_tags (array: rumor/hack/regulation), priority (low/medium/high), language (detected). Причины приоритета — 1 предложение.
        """,
        
        "translation": """
Ты — эксперт по криптовалютам и переводчик. Твоя задача: на основе исходного текста на {{lang}} подготовить:
1) качественный перевод на русский (без кальки с оригинала, естественная русская речь),
2) краткий пересказ в 3-5 предложениях, понятный неспециалисту,
3) список 3 ключевых фактов и 2 возможных последствий для рынка.
Соблюдай тон: нейтрально-аналитический. Если в тексте встречаются термины/события, добавь короткое пояснение в скобках. Если статья содержит непроверяемые слухи — пометь как "неподтверждённо".
Ограничение: итоговый перевод не должен содержать фраз длинее 40 слов.
        """,
        
        "paraphrase": """
Ты — редактор телеграм-канала с человечным, но аналитическим тоном. На входе — исходный текст (перевод) и краткий пересказ.
Требуется сгенерировать уникальную статью длиной 200–450 слов, которая:
- полностью перефразирует исходник (никаких длинных фрагментов копипаста),
- включает 1–2 личные ремарки от автора (например: "напоминает нам, что..."),
- если есть пересечения с прошлой публикацией — вставь фразу вида: "Мы писали об этом 12.07.2025 — тогда..." и кратко свяжи события,
- в конце добавь мягкий CTA: "Если хотите полное досье — ссылка в описании" и при необходимости вставь аффил. ссылку.
- предложи 2 варианта заголовка (короткий и расширенный) и 3 тега/хэштега.

Проверки: итог должен иметь плагиат-score < {{threshold}} по внутреннему метрике. Если материал — слух, пометь.
        """,
        
        "image_prompt": """
Magazine-style crypto cover, background: subtle candlestick chart, foreground: anonymous trader silhouette checking phone, no real logos, mood: urgent-analytic, style: photorealistic + cinematic lighting, add headline overlay: '{{headline_short}}', format: 1200x675, aspect:16:9. Avoid: copyrighted logos, real faces.
        """
    }


class AffiliateConfig:
    """Affiliate links configuration"""
    
    AFFILIATE_LINKS = [
        {
            "name": "Binance",
            "url": "https://accounts.binance.com/register?ref=YOUR_REF",
            "text": "Если хотите быстрее заходить на биржу — используйте партнёрскую ссылку",
            "weight": 0.4
        },
        {
            "name": "ByBit", 
            "url": "https://www.bybit.com/register?affiliate_id=YOUR_ID",
            "text": "Для торговли с бонусами — партнёрская ссылка в описании",
            "weight": 0.3
        },
        {
            "name": "OKX",
            "url": "https://www.okx.com/join/YOUR_CODE",
            "text": "Хотите попробовать другую биржу? Ссылка с бонусом",
            "weight": 0.3
        }
    ]
    
    DISCLOSURE_TEXT = "содержит партнёрскую ссылку"


# Initialize settings
settings = Settings()
source_config = SourceConfig()
llm_config = LLMConfig()
affiliate_config = AffiliateConfig()
