"""
Image Service for in-memory image processing.

Handles image download, resizing, and base64 encoding
without writing to disk for privacy compliance.
"""

from io import BytesIO
import base64
from typing import Optional, Tuple
from PIL import Image
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass  # Allow running without heic support if dependency missing

from src.services.line_service import get_line_service
from src.utils.logger import get_logger
from src.utils.validators import validate_image_content_type
import httpx

logger = get_logger("services.image")

# Maximum dimension (longest side) before resizing
MAX_IMAGE_DIMENSION = 1920

# Supported image formats
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


class ImageProcessingError(Exception):
    """Raised when image processing fails."""
    pass


async def download_and_process_image(
    message_id: str,
    max_dimension: int = MAX_IMAGE_DIMENSION,
    image_url: Optional[str] = None,
) -> Optional[str]:
    """
    Download image from LINE and process for LLM.
    
    Downloads image into memory, resizes if needed, and
    returns base64-encoded string. Never writes to disk.
    
    Args:
        message_id: LINE message ID containing the image
        max_dimension: Maximum dimension before resizing
        image_url: Optional direct URL to download image from (skips LINE API)
        
    Returns:
        Base64-encoded image string, or None if failed
    """
    line_service = get_line_service()
    
    try:
        content = None
        content_type = None

        if image_url:
            # Download directly from URL (for bot-sent images)
            logger.debug(f"Downloading image from URL: {image_url}")
            async with httpx.AsyncClient() as client:
                response = await client.get(image_url, timeout=30.0)
                if response.status_code == 200:
                    content = BytesIO(response.content)
                    content_type = response.headers.get("content-type")
                else:
                    logger.error(f"Failed to download image from URL: {response.status_code}")
                    return None
        else:
            # Download image content from LINE API
            content, content_type = await line_service.get_message_content_with_type(message_id)
        
        if content is None:
            logger.error(f"Failed to download image: {message_id}")
            return None
        
        # Validate content type
        if content_type and not validate_image_content_type(content_type):
            logger.warning(f"Unsupported content type: {content_type}")
            # Try to process anyway - PIL might handle it
        
        # Process image in memory
        return process_image_bytes(content, max_dimension)
        
    except Exception as e:
        logger.error(f"Image download/processing error: {e}", exc_info=True)
        return None


def process_image_bytes(
    image_bytes: BytesIO,
    max_dimension: int = MAX_IMAGE_DIMENSION,
) -> Optional[str]:
    """
    Process image bytes: resize if needed and encode to base64.
    
    Args:
        image_bytes: BytesIO containing image data
        max_dimension: Maximum dimension (longest side)
        
    Returns:
        Base64-encoded image string
        
    Raises:
        ImageProcessingError: If processing fails
    """
    try:
        # Reset stream position
        image_bytes.seek(0)
        
        # Open image with PIL
        with Image.open(image_bytes) as img:
            # Log original size
            original_size = img.size
            logger.debug(f"Original image size: {original_size}")
            
            # Check format
            if img.format not in SUPPORTED_FORMATS:
                logger.warning(f"Converting {img.format} to JPEG")
            
            # Resize if needed (preserve aspect ratio)
            img = resize_image(img, max_dimension)
            
            # Convert to RGB if necessary (for JPEG encoding)
            if img.mode in ("RGBA", "P"):
                # Create white background for transparency
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")
            
            # Encode to JPEG in memory
            output_buffer = BytesIO()
            img.save(output_buffer, format="JPEG", quality=85, optimize=True)
            
            # Get base64 encoded string
            output_buffer.seek(0)
            base64_str = base64.b64encode(output_buffer.read()).decode("utf-8")
            
            logger.info(
                f"Image processed: {original_size} -> {img.size}, "
                f"base64 length: {len(base64_str)}"
            )
            
            return base64_str
            
    except Exception as e:
        logger.error(f"Image processing error: {e}", exc_info=True)
        raise ImageProcessingError(f"Failed to process image: {e}")


def resize_image(img: Image.Image, max_dimension: int) -> Image.Image:
    """
    Resize image if it exceeds max dimension.
    
    Preserves aspect ratio, only downsizes (never upscales).
    
    Args:
        img: PIL Image object
        max_dimension: Maximum allowed dimension
        
    Returns:
        Resized (or original) PIL Image
    """
    width, height = img.size
    
    # Find the longest side
    longest_side = max(width, height)
    
    # Only resize if exceeds max
    if longest_side <= max_dimension:
        return img
    
    # Calculate new size preserving aspect ratio
    ratio = max_dimension / longest_side
    new_width = int(width * ratio)
    new_height = int(height * ratio)
    
    # Use high-quality downsampling
    resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    logger.debug(f"Image resized: {width}x{height} -> {new_width}x{new_height}")
    
    return resized


def get_image_dimensions(image_bytes: BytesIO) -> Tuple[int, int]:
    """
    Get image dimensions without fully loading.
    
    Args:
        image_bytes: BytesIO containing image data
        
    Returns:
        Tuple of (width, height)
    """
    image_bytes.seek(0)
    with Image.open(image_bytes) as img:
        return img.size


def estimate_base64_size(image_bytes: BytesIO) -> int:
    """
    Estimate base64 encoded size.
    
    Args:
        image_bytes: BytesIO containing image data
        
    Returns:
        Estimated base64 string length
    """
    image_bytes.seek(0)
    raw_size = len(image_bytes.read())
    # Base64 encoding increases size by ~33%
    return int(raw_size * 1.37)


def convert_to_jpeg(
    image_bytes: bytes,
    max_dimension: Optional[int] = None,  # None = keep original size
) -> Optional[bytes]:
    """
    Convert image bytes (any format including HEIC) to JPEG bytes.
    Optionally resizes if max_dimension is provided.
    
    Args:
        image_bytes: Raw image data
        max_dimension: Maximum dimension (longest side), or None
        
    Returns:
        JPEG image bytes, or None if conversion failed
    """
    try:
        # Load into memory
        io = BytesIO(image_bytes)
        
        # Open with PIL (handles HEIC if pillow-heif is registered)
        with Image.open(io) as img:
            # Convert to RGB (handles RGBA, P, etc.)
            if img.mode != "RGB":
                img = img.convert("RGB")
            
            # Resize if needed
            if max_dimension:
                img = resize_image(img, max_dimension)
            
            # Save as JPEG
            output = BytesIO()
            img.save(output, format="JPEG", quality=85, optimize=True)
            return output.getvalue()
            
    except Exception as e:
        logger.error(f"Image conversion failed: {e}")
        return None
