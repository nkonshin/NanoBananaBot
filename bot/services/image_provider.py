"""Image provider service for AI image generation."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    """Result of an image generation/edit operation."""
    
    success: bool
    image_url: Optional[str] = None
    error: Optional[str] = None


class ImageProvider(ABC):
    """Abstract base class for image generation providers."""
    
    @abstractmethod
    async def generate(self, prompt: str) -> GenerationResult:
        """
        Generate an image from a text prompt.
        
        Args:
            prompt: Text description of the image to generate
        
        Returns:
            GenerationResult with success status and image URL or error
        """
        pass
    
    @abstractmethod
    async def edit(self, image_source: str, prompt: str, bot_token: str = None) -> GenerationResult:
        """
        Edit an existing image based on a text prompt.
        
        Args:
            image_source: URL or Telegram file_id of the source image
            prompt: Text description of the desired changes
            bot_token: Telegram bot token (required if image_source is file_id)
        
        Returns:
            GenerationResult with success status and image URL or error
        """
        pass


class OpenAIImageProvider(ImageProvider):
    """OpenAI Images API implementation of ImageProvider."""
    
    def __init__(self, api_key: str, model: str = "gpt-image-1"):
        """
        Initialize OpenAI image provider.
        
        Args:
            api_key: OpenAI API key
            model: Model to use for generation (default: gpt-image-1)
        """
        self.api_key = api_key
        self.model = model
        self.client = AsyncOpenAI(api_key=api_key)
    
    async def generate(self, prompt: str) -> GenerationResult:
        """
        Generate an image using OpenAI Images API.
        
        Args:
            prompt: Text description of the image to generate
        
        Returns:
            GenerationResult with success status and image URL or error
        """
        logger.info(f"Generating image with prompt: {prompt[:100]}...")
        
        try:
            response = await self.client.images.generate(
                model=self.model,
                prompt=prompt,
                n=1,
                size="1024x1024",
            )
            
            image_url = response.data[0].url
            logger.info(f"Image generated successfully: {image_url}")
            
            return GenerationResult(
                success=True,
                image_url=image_url,
            )
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Image generation failed: {error_msg}")
            
            return GenerationResult(
                success=False,
                error=error_msg,
            )
    
    async def edit(self, image_source: str, prompt: str, bot_token: str = None) -> GenerationResult:
        """
        Edit an image using OpenAI Images API.
        
        Args:
            image_source: URL or Telegram file_id of the source image
            prompt: Text description of the desired changes
            bot_token: Telegram bot token (required if image_source is file_id)
        
        Returns:
            GenerationResult with success status and image URL or error
        """
        logger.info(f"Editing image {image_source} with prompt: {prompt[:100]}...")
        
        try:
            import httpx
            import io
            
            # Check if image_source is a URL or Telegram file_id
            if image_source.startswith(('http://', 'https://')):
                # It's a URL - download directly
                async with httpx.AsyncClient() as http_client:
                    img_response = await http_client.get(image_source)
                    img_response.raise_for_status()
                    image_data = img_response.content
            else:
                # It's a Telegram file_id - download from Telegram
                if not bot_token:
                    raise ValueError("bot_token required for Telegram file_id")
                
                from aiogram import Bot
                
                bot = Bot(token=bot_token)
                
                # Get file info
                file = await bot.get_file(image_source)
                
                # Download file
                file_bytes = io.BytesIO()
                await bot.download_file(file.file_path, file_bytes)
                image_data = file_bytes.getvalue()
                
                await bot.session.close()
                
                logger.info(f"Downloaded image from Telegram: {len(image_data)} bytes")
            
            # Use OpenAI edit endpoint
            # Note: OpenAI Images API edit endpoint requires PNG format
            # We'll send the image as-is and let OpenAI handle it
            response = await self.client.images.edit(
                model=self.model,
                image=image_data,
                prompt=prompt,
                n=1,
                size="1024x1024",
            )
            
            result_url = response.data[0].url
            logger.info(f"Image edited successfully: {result_url}")
            
            return GenerationResult(
                success=True,
                image_url=result_url,
            )
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Image edit failed: {error_msg}")
            
            return GenerationResult(
                success=False,
                error=error_msg,
            )
