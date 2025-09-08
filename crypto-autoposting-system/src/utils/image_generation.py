"""
Image generation and processing service
"""
import logging
import asyncio
import json
import hashlib
import aiohttp
import io
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from PIL import Image, ImageDraw, ImageFont
import requests

from ..config import settings, llm_config
from ..models import SessionLocal, GeneratedImage, ProcessedContent
from ..utils.redis_client import RedisClient
from ..utils.storage import StorageService

logger = logging.getLogger(__name__)


class ImageGenerationService:
    """Image generation and processing service"""
    
    def __init__(self):
        self.session = SessionLocal()
        self.redis_client = RedisClient()
        self.storage = StorageService()
        
    async def generate_post_image(self, processed_content_id: str, headline: str, content_type: str = "news") -> Optional[str]:
        """Generate main image for a post"""
        try:
            # Check if image already exists
            existing_image = self.session.query(GeneratedImage).filter(
                GeneratedImage.processed_content_id == processed_content_id,
                GeneratedImage.is_primary == True
            ).first()
            
            if existing_image:
                return existing_image.image_url
            
            # Generate prompt for image
            image_prompt = await self._create_image_prompt(headline, content_type)
            
            # Try different generation services
            image_url = None
            
            # Try Stable Diffusion first
            if settings.stability_api_key:
                image_url = await self._generate_with_stability(image_prompt)
            
            # Fallback to other services or create text-based image
            if not image_url:
                image_url = await self._create_text_based_image(headline, content_type)
            
            if image_url:
                # Save to database
                generated_image = GeneratedImage(
                    processed_content_id=processed_content_id,
                    image_url=image_url,
                    image_type="generated",
                    generation_prompt=image_prompt,
                    generator="stability_ai" if settings.stability_api_key else "text_based",
                    width=1200,
                    height=675,
                    format="png",
                    is_primary=True
                )
                
                self.session.add(generated_image)
                self.session.commit()
                
                logger.info(f"Generated image for content {processed_content_id}")
                return image_url
            
            return None
            
        except Exception as e:
            logger.error(f"Image generation failed for {processed_content_id}: {e}")
            return None
    
    async def _create_image_prompt(self, headline: str, content_type: str) -> str:
        """Create image generation prompt based on content"""
        try:
            # Base prompt template
            base_prompt = llm_config.PROMPTS["image_prompt"]
            
            # Customize based on content type
            style_modifiers = {
                "news": "breaking news style, urgent, professional",
                "analysis": "analytical, charts, data visualization",
                "technical": "technical diagram, blockchain visualization",
                "regulatory": "legal, official, government style",
                "hack": "security, warning, red colors",
                "leak": "exclusive, insider information, mysterious"
            }
            
            style = style_modifiers.get(content_type, "professional, modern")
            
            # Create final prompt
            prompt = base_prompt.format(headline_short=headline)
            prompt += f", style: {style}, cryptocurrency theme"
            
            return prompt
            
        except Exception as e:
            logger.error(f"Failed to create image prompt: {e}")
            return "Cryptocurrency news cover image, professional style"
    
    async def _generate_with_stability(self, prompt: str) -> Optional[str]:
        """Generate image using Stability AI"""
        try:
            url = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image"
            
            headers = {
                "Authorization": f"Bearer {settings.stability_api_key}",
                "Content-Type": "application/json",
            }
            
            data = {
                "text_prompts": [
                    {
                        "text": prompt,
                        "weight": 1.0
                    },
                    {
                        "text": "blurry, bad quality, distorted, watermark, signature, text",
                        "weight": -1.0
                    }
                ],
                "cfg_scale": 7,
                "height": 675,
                "width": 1200,
                "samples": 1,
                "steps": 30,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # Get the generated image
                        if result.get("artifacts"):
                            image_data = result["artifacts"][0]["base64"]
                            
                            # Upload to storage
                            image_url = await self.storage.upload_image_from_base64(
                                image_data, 
                                f"generated_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
                            )
                            
                            return image_url
                    else:
                        logger.warning(f"Stability AI request failed: {response.status}")
            
            return None
            
        except Exception as e:
            logger.error(f"Stability AI generation failed: {e}")
            return None
    
    async def _create_text_based_image(self, headline: str, content_type: str) -> Optional[str]:
        """Create a simple text-based image as fallback"""
        try:
            # Create image
            width, height = 1200, 675
            
            # Choose colors based on content type
            color_schemes = {
                "news": ("#1a1a1a", "#ffffff", "#f39c12"),
                "analysis": ("#2c3e50", "#ffffff", "#3498db"),
                "technical": ("#34495e", "#ffffff", "#9b59b6"),
                "regulatory": ("#8b0000", "#ffffff", "#ff6b6b"),
                "hack": ("#000000", "#ff0000", "#ffffff"),
                "leak": ("#2f1b14", "#d4af37", "#ffffff")
            }
            
            bg_color, text_color, accent_color = color_schemes.get(content_type, color_schemes["news"])
            
            # Create image
            img = Image.new('RGB', (width, height), color=bg_color)
            draw = ImageDraw.Draw(img)
            
            # Try to load font (fallback to default if not available)
            try:
                font_large = ImageFont.truetype("arial.ttf", 48)
                font_small = ImageFont.truetype("arial.ttf", 24)
            except:
                font_large = ImageFont.load_default()
                font_small = ImageFont.load_default()
            
            # Draw background pattern
            for i in range(0, width, 100):
                draw.line([(i, 0), (i, height)], fill=accent_color, width=1)
            
            # Wrap headline text
            wrapped_headline = self._wrap_text(headline, 40)
            
            # Calculate text position
            bbox = draw.textbbox((0, 0), wrapped_headline, font=font_large)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            x = (width - text_width) // 2
            y = (height - text_height) // 2 - 50
            
            # Draw text with shadow
            draw.text((x+2, y+2), wrapped_headline, font=font_large, fill="#000000", anchor="mm")
            draw.text((x, y), wrapped_headline, font=font_large, fill=text_color, anchor="mm")
            
            # Add crypto indicator
            crypto_text = "CRYPTO NEWS"
            draw.text((50, height-50), crypto_text, font=font_small, fill=accent_color)
            
            # Save to storage
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='PNG', quality=95)
            img_buffer.seek(0)
            
            image_url = await self.storage.upload_image_from_buffer(
                img_buffer,
                f"text_image_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
            )
            
            return image_url
            
        except Exception as e:
            logger.error(f"Text-based image creation failed: {e}")
            return None
    
    def _wrap_text(self, text: str, width: int) -> str:
        """Wrap text to specified width"""
        words = text.split()
        lines = []
        current_line = []
        current_length = 0
        
        for word in words:
            if current_length + len(word) + 1 <= width:
                current_line.append(word)
                current_length += len(word) + 1
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]
                current_length = len(word)
        
        if current_line:
            lines.append(" ".join(current_line))
        
        return "\n".join(lines)
    
    async def find_stock_image(self, query: str) -> Optional[str]:
        """Find appropriate stock image for content"""
        try:
            # This would integrate with stock photo APIs like Unsplash, Pexels, etc.
            # For now, return None to use generated images
            
            # Example Unsplash integration:
            # unsplash_url = f"https://api.unsplash.com/search/photos?query={query}&client_id={UNSPLASH_ACCESS_KEY}"
            # ... implementation
            
            return None
            
        except Exception as e:
            logger.error(f"Stock image search failed: {e}")
            return None
    
    async def create_thumbnail(self, image_url: str, size: Tuple[int, int] = (300, 169)) -> Optional[str]:
        """Create thumbnail from existing image"""
        try:
            # Download original image
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        
                        # Create thumbnail
                        img = Image.open(io.BytesIO(image_data))
                        img.thumbnail(size, Image.Resampling.LANCZOS)
                        
                        # Save thumbnail
                        thumb_buffer = io.BytesIO()
                        img.save(thumb_buffer, format='PNG', quality=85)
                        thumb_buffer.seek(0)
                        
                        thumbnail_url = await self.storage.upload_image_from_buffer(
                            thumb_buffer,
                            f"thumb_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
                        )
                        
                        return thumbnail_url
            
            return None
            
        except Exception as e:
            logger.error(f"Thumbnail creation failed: {e}")
            return None
    
    async def add_watermark(self, image_url: str, watermark_text: str = "Crypto News") -> Optional[str]:
        """Add watermark to image"""
        try:
            # Download original image
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        
                        # Add watermark
                        img = Image.open(io.BytesIO(image_data))
                        draw = ImageDraw.Draw(img)
                        
                        # Position watermark
                        width, height = img.size
                        try:
                            font = ImageFont.truetype("arial.ttf", 20)
                        except:
                            font = ImageFont.load_default()
                        
                        bbox = draw.textbbox((0, 0), watermark_text, font=font)
                        text_width = bbox[2] - bbox[0]
                        
                        x = width - text_width - 20
                        y = height - 30
                        
                        # Draw watermark with transparency
                        draw.text((x+1, y+1), watermark_text, font=font, fill=(0, 0, 0, 128))
                        draw.text((x, y), watermark_text, font=font, fill=(255, 255, 255, 200))
                        
                        # Save watermarked image
                        watermark_buffer = io.BytesIO()
                        img.save(watermark_buffer, format='PNG', quality=95)
                        watermark_buffer.seek(0)
                        
                        watermarked_url = await self.storage.upload_image_from_buffer(
                            watermark_buffer,
                            f"watermarked_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
                        )
                        
                        return watermarked_url
            
            return None
            
        except Exception as e:
            logger.error(f"Watermark addition failed: {e}")
            return None
    
    async def process_content_images(self, processed_content_id: str) -> List[str]:
        """Process all images for a piece of content"""
        try:
            processed_content = self.session.query(ProcessedContent).get(processed_content_id)
            if not processed_content:
                return []
            
            image_urls = []
            
            # Generate main image
            main_image = await self.generate_post_image(
                processed_content_id,
                processed_content.headline_short or processed_content.headline_long or "Crypto News",
                processed_content.content_type
            )
            
            if main_image:
                image_urls.append(main_image)
                
                # Create thumbnail
                thumbnail = await self.create_thumbnail(main_image)
                if thumbnail:
                    image_urls.append(thumbnail)
            
            return image_urls
            
        except Exception as e:
            logger.error(f"Image processing failed for content {processed_content_id}: {e}")
            return []
    
    def close(self):
        """Close database connection"""
        self.session.close()


# Standalone functions
async def generate_image_for_content(processed_content_id: str, headline: str, content_type: str = "news") -> Optional[str]:
    """Generate image for content"""
    service = ImageGenerationService()
    try:
        return await service.generate_post_image(processed_content_id, headline, content_type)
    finally:
        service.close()


async def create_simple_image(text: str, content_type: str = "news") -> Optional[str]:
    """Create simple text-based image"""
    service = ImageGenerationService()
    try:
        return await service._create_text_based_image(text, content_type)
    finally:
        service.close()


if __name__ == "__main__":
    # Test image generation
    import asyncio
    
    async def test():
        service = ImageGenerationService()
        try:
            image_url = await service._create_text_based_image(
                "Bitcoin Reaches New All-Time High", 
                "news"
            )
            print(f"Generated image: {image_url}")
        finally:
            service.close()
    
    asyncio.run(test())
