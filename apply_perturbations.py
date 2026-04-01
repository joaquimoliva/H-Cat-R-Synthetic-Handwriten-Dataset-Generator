#!/usr/bin/env python3
"""
Perturbation module for synthetic handwriting dataset.
Applies realistic degradations to simulate scanned/photographed documents.

Simplified to 3 effective perturbations:
- blur: Gaussian blur (most visible)
- rotation: Slight rotation (simulates misalignment)
- contrast: Reduced contrast (washes out text)

Usage:
    from apply_perturbations import PerturbationPipeline
    
    pipeline = PerturbationPipeline(quality_distribution=(40, 40, 20))
    degraded_image, metadata = pipeline.apply(image)
"""

import random
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
from io import BytesIO
from dataclasses import dataclass, field, asdict
from typing import Tuple, Optional, Dict, Any
from enum import Enum


class QualityLevel(Enum):
    CLEAN = "clean"
    DEGRADED = "degraded"
    SEVERE = "severe"


@dataclass
class PerturbationParams:
    """Stores the parameters of applied perturbations for metadata."""
    quality: str = "clean"
    blur_radius: Optional[float] = None
    rotation_angle: Optional[float] = None
    contrast_factor: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}


# Perturbation ranges per quality level
PERTURBATION_RANGES = {
    QualityLevel.CLEAN: {
        # No perturbations
    },
    QualityLevel.DEGRADED: {
        "blur_radius": (0.5, 1.2),
        "rotation_angle": (-1.0, 1.0),
        "contrast_factor": (0.65, 0.80),
    },
    QualityLevel.SEVERE: {
        "blur_radius": (2.0, 3.5),
        "rotation_angle": (-2.0, 2.0),
        "contrast_factor": (0.30, 0.50),
    },
}

# Probability of applying each perturbation (when quality is not clean)
PERTURBATION_PROBABILITIES = {
    "blur": 0.7,
    "rotation": 0.5,
    "contrast": 0.6,
}


def apply_gaussian_blur(image: Image.Image, radius: float) -> Image.Image:
    """Apply Gaussian blur to simulate out-of-focus scan/photo."""
    return image.filter(ImageFilter.GaussianBlur(radius=radius))


def apply_rotation(image: Image.Image, angle: float, fill_color=(255, 255, 255)) -> Image.Image:
    """
    Rotate image slightly to simulate misaligned document.
    Expands canvas during rotation, then crops back to original size
    to avoid fill color mismatch with textured backgrounds.
    """
    original_size = image.size
    
    # Rotate with expand to avoid cutting content
    rotated = image.rotate(
        angle, 
        resample=Image.BICUBIC, 
        expand=True,
        fillcolor=fill_color
    )
    
    # Crop back to original size from center (removes fill color edges)
    new_width, new_height = rotated.size
    left = (new_width - original_size[0]) // 2
    top = (new_height - original_size[1]) // 2
    right = left + original_size[0]
    bottom = top + original_size[1]
    
    cropped = rotated.crop((left, top, right, bottom))
    return cropped


def apply_gaussian_noise(image: Image.Image, sigma: int) -> Image.Image:
    """Add Gaussian noise to simulate sensor noise."""
    arr = np.array(image, dtype=np.float32)
    noise = np.random.normal(0, sigma, arr.shape)
    noisy = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(noisy)


def apply_jpeg_compression(image: Image.Image, quality: int) -> Image.Image:
    """Apply JPEG compression artifacts."""
    buffer = BytesIO()
    # Convert to RGB if necessary (JPEG doesn't support RGBA)
    if image.mode == 'RGBA':
        rgb_image = Image.new('RGB', image.size, (255, 255, 255))
        rgb_image.paste(image, mask=image.split()[3])
        image = rgb_image
    elif image.mode != 'RGB':
        image = image.convert('RGB')
    
    image.save(buffer, format='JPEG', quality=quality)
    buffer.seek(0)
    return Image.open(buffer).copy()


def apply_brightness(image: Image.Image, factor: float) -> Image.Image:
    """Adjust brightness. factor < 1 = darker, > 1 = brighter."""
    enhancer = ImageEnhance.Brightness(image)
    return enhancer.enhance(factor)


def apply_contrast(image: Image.Image, factor: float) -> Image.Image:
    """Adjust contrast. factor < 1 = less contrast, > 1 = more contrast."""
    enhancer = ImageEnhance.Contrast(image)
    return enhancer.enhance(factor)


class PerturbationPipeline:
    """
    Pipeline for applying perturbations with configurable quality distribution.
    
    Args:
        quality_distribution: Tuple of (clean%, degraded%, severe%) percentages.
                            Must sum to 100. Default: (40, 40, 20)
        seed: Random seed for reproducibility. Default: None
    """
    
    def __init__(
        self, 
        quality_distribution: Tuple[int, int, int] = (40, 40, 20),
        seed: Optional[int] = None
    ):
        assert sum(quality_distribution) == 100, "Distribution must sum to 100"
        self.quality_distribution = quality_distribution
        
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
    
    def _select_quality_level(self) -> QualityLevel:
        """Randomly select quality level based on distribution."""
        r = random.randint(1, 100)
        clean_threshold = self.quality_distribution[0]
        degraded_threshold = clean_threshold + self.quality_distribution[1]
        
        if r <= clean_threshold:
            return QualityLevel.CLEAN
        elif r <= degraded_threshold:
            return QualityLevel.DEGRADED
        else:
            return QualityLevel.SEVERE
    
    def _get_random_param(self, param_range) -> float:
        """
        Get random parameter within range.
        Supports:
        - 2 values (min, max): simple range
        - 4 values (min1, max1, min2, max2): two sub-ranges (avoids middle zone)
        """
        if len(param_range) == 2:
            return random.uniform(param_range[0], param_range[1])
        elif len(param_range) == 4:
            # Two sub-ranges: randomly pick one, then sample from it
            if random.random() < 0.5:
                return random.uniform(param_range[0], param_range[1])  # Lower range
            else:
                return random.uniform(param_range[2], param_range[3])  # Upper range
        else:
            return param_range[0]  # Fallback
    
    def _detect_background_color(self, image: Image.Image) -> Tuple[int, int, int]:
        """Detect the dominant background color (usually corners)."""
        # Sample corners
        w, h = image.size
        corners = [
            image.getpixel((0, 0)),
            image.getpixel((w-1, 0)),
            image.getpixel((0, h-1)),
            image.getpixel((w-1, h-1)),
        ]
        # Handle different modes
        if image.mode == 'L':
            avg = int(sum(corners) / 4)
            return (avg, avg, avg)
        elif image.mode in ('RGB', 'RGBA'):
            # Average RGB, ignore alpha
            r = int(sum(c[0] for c in corners) / 4)
            g = int(sum(c[1] for c in corners) / 4)
            b = int(sum(c[2] for c in corners) / 4)
            return (r, g, b)
        return (255, 255, 255)  # Default white
    
    def apply(
        self, 
        image: Image.Image,
        force_quality: Optional[QualityLevel] = None
    ) -> Tuple[Image.Image, PerturbationParams]:
        """
        Apply perturbations to an image.
        
        Args:
            image: PIL Image to perturb
            force_quality: Force a specific quality level (for testing)
        
        Returns:
            Tuple of (perturbed_image, perturbation_params)
        """
        # Select quality level
        quality = force_quality or self._select_quality_level()
        params = PerturbationParams(quality=quality.value)
        
        # If clean, return as-is
        if quality == QualityLevel.CLEAN:
            return image, params
        
        # Get ranges for this quality level
        ranges = PERTURBATION_RANGES[quality]
        
        # Ensure RGB mode for processing
        original_mode = image.mode
        if image.mode == 'RGBA':
            alpha = image.split()[3]
            image = image.convert('RGB')
        elif image.mode == 'L':
            image = image.convert('RGB')
        
        # Detect background color for rotation fill
        bg_color = self._detect_background_color(image)
        
        # For SEVERE: all 3 perturbations always applied
        # For DEGRADED: each perturbation applied by probability
        if quality == QualityLevel.SEVERE:
            # Always apply all 3 for SEVERE
            to_apply = {"blur": True, "rotation": True, "contrast": True}
        else:
            # DEGRADED: apply by probability, but ensure at least 1
            to_apply = {
                "blur": random.random() < PERTURBATION_PROBABILITIES["blur"],
                "rotation": random.random() < PERTURBATION_PROBABILITIES["rotation"],
                "contrast": random.random() < PERTURBATION_PROBABILITIES["contrast"],
            }
            # Ensure at least one perturbation for DEGRADED
            if not any(to_apply.values()):
                to_apply[random.choice(["blur", "rotation", "contrast"])] = True
        
        # 1. Rotation (apply first)
        if to_apply["rotation"]:
            angle = self._get_random_param(ranges["rotation_angle"])
            image = apply_rotation(image, angle, fill_color=bg_color)
            params.rotation_angle = round(angle, 2)
        
        # 2. Blur
        if to_apply["blur"]:
            radius = self._get_random_param(ranges["blur_radius"])
            image = apply_gaussian_blur(image, radius)
            params.blur_radius = round(radius, 2)
        
        # 3. Contrast (apply last)
        if to_apply["contrast"]:
            factor = self._get_random_param(ranges["contrast_factor"])
            image = apply_contrast(image, factor)
            params.contrast_factor = round(factor, 2)
        
        return image, params


def demo():
    """Demonstrate perturbation effects on a sample image."""
    # Create a simple test image with text-like content
    from PIL import ImageDraw, ImageFont
    
    img = Image.new('RGB', (800, 200), (245, 245, 240))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except:
        font = ImageFont.load_default()
    
    draw.text((50, 70), "Sample handwritten text", fill=(30, 30, 30), font=font)
    
    # Test each quality level
    pipeline = PerturbationPipeline(quality_distribution=(33, 34, 33), seed=42)
    
    print("Perturbation Demo")
    print("=" * 50)
    
    for quality in QualityLevel:
        perturbed, params = pipeline.apply(img.copy(), force_quality=quality)
        print(f"\n{quality.value.upper()}:")
        print(f"  Params: {params.to_dict()}")
        perturbed.save(f"demo_{quality.value}.png")
        print(f"  Saved: demo_{quality.value}.png")


if __name__ == "__main__":
    demo()
