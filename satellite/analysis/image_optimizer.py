"""
Cloud-optimized GeoTIFF (COG) creation and image processing utilities
"""

import os
import logging
from typing import Tuple, Optional, Dict, Any
from pathlib import Path

import rasterio
from rasterio.io import MemoryFile
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.enums import ColorInterp
from rasterio.shutil import copy as rio_copy
from rasterio.windows import Window
from PIL import Image
import numpy as np
from django.contrib.gis.geos import Polygon, Point
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)


class ImageOptimizer:
    """Handles satellite image optimization and COG creation"""

    def __init__(self, input_path: str):
        self.input_path = input_path
        self.src_dataset = None

    def __enter__(self):
        self.src_dataset = rasterio.open(self.input_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.src_dataset:
            self.src_dataset.close()

    def get_image_metadata(self) -> Dict[str, Any]:
        """Extract comprehensive metadata from satellite image"""
        if not self.src_dataset:
            raise ValueError("Dataset not opened. Use context manager.")

        bounds = self.src_dataset.bounds

        metadata = {
            "width": self.src_dataset.width,
            "height": self.src_dataset.height,
            "bands": self.src_dataset.count,
            "crs": str(self.src_dataset.crs) if self.src_dataset.crs else None,
            "bounds": {
                "left": bounds.left,
                "bottom": bounds.bottom,
                "right": bounds.right,
                "top": bounds.top,
            },
            "resolution": self.src_dataset.res,
            "dtype": (
                str(self.src_dataset.dtypes[0]) if self.src_dataset.dtypes else None
            ),
            "nodata": self.src_dataset.nodata,
        }

        return metadata

    def get_geographic_bounds(self) -> Tuple[Polygon, Point]:
        """
        Calculate geographic bounds and center point
        Returns: (bounds_polygon, center_point) in WGS84
        """
        if not self.src_dataset:
            raise ValueError("Dataset not opened. Use context manager.")

        # Get bounds in source CRS
        bounds = self.src_dataset.bounds

        # Convert to WGS84 if necessary
        if self.src_dataset.crs and self.src_dataset.crs.to_string() != "EPSG:4326":
            from rasterio.warp import transform_bounds

            bounds_4326 = transform_bounds(
                self.src_dataset.crs,
                "EPSG:4326",
                bounds.left,
                bounds.bottom,
                bounds.right,
                bounds.top,
            )
            left, bottom, right, top = bounds_4326
        else:
            left, bottom, right, top = (
                bounds.left,
                bounds.bottom,
                bounds.right,
                bounds.top,
            )

        # Create polygon for bounds
        coords = [
            (left, bottom),
            (right, bottom),
            (right, top),
            (left, top),
            (left, bottom),
        ]
        bounds_polygon = Polygon(coords, srid=4326)

        # Calculate center point
        center_lon = (left + right) / 2
        center_lat = (bottom + top) / 2
        center_point = Point(center_lon, center_lat, srid=4326)

        return bounds_polygon, center_point

    def create_cog(
        self,
        output_path: str,
        compression: str = "JPEG",
        quality: int = 85,
        overview_levels: Optional[list] = None,
    ) -> bool:
        """
        Create a cloud-optimized GeoTIFF (COG) from the input image using windowed reading
        Processes image in chunks to handle large files without loading entire bands into memory

        Args:
            output_path: Path where the COG will be saved
            compression: Compression method (JPEG, LZW, DEFLATE)
            quality: JPEG quality (1-100)
            overview_levels: List of overview levels (e.g., [2, 4, 8, 16])

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.src_dataset:
            raise ValueError("Dataset not opened. Use context manager.")

        if overview_levels is None:
            overview_levels = [2, 4, 8, 16]

        try:
            # COG profile settings
            cog_profile = {
                "driver": "GTiff",
                "interleave": "pixel",
                "tiled": True,
                "blockxsize": 512,
                "blockysize": 512,
                "compress": compression,
                "BIGTIFF": "IF_SAFER",
            }

            # Only set photometric for JPEG compression if we have 3 bands
            if compression == "JPEG" and self.src_dataset.count >= 3:
                cog_profile["photometric"] = "YCbCr"
                cog_profile["jpeg_quality"] = quality
            elif compression == "JPEG":
                # For single or 2-band images, use no photometric interpretation with JPEG
                # JPEG compression with photometric YCbCr requires exactly 3 bands
                cog_profile["compress"] = "DEFLATE"  # Use DEFLATE for non-RGB images

            # Update with source dataset profile
            profile = self.src_dataset.profile.copy()
            profile.update(cog_profile)

            # Create output directory if it doesn't exist
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # Write COG with windowed reading to avoid loading entire image into memory
            from rasterio.windows import Window

            with rasterio.open(output_path, "w", **profile) as dst:
                # Copy data in windows to avoid memory issues with large files
                window_size = 1024
                height = self.src_dataset.height
                width = self.src_dataset.width

                for band_idx in range(1, self.src_dataset.count + 1):
                    logger.info(f"Processing band {band_idx}/{self.src_dataset.count}")

                    # Process band in windows
                    for y_start in range(0, height, window_size):
                        for x_start in range(0, width, window_size):
                            # Calculate window dimensions
                            y_end = min(y_start + window_size, height)
                            x_end = min(x_start + window_size, width)
                            window = Window(
                                x_start, y_start, x_end - x_start, y_end - y_start
                            )

                            # Read window data
                            data = self.src_dataset.read(band_idx, window=window)

                            # Write window data
                            dst.write(data, band_idx, window=window)

                # Copy metadata
                dst.update_tags(**self.src_dataset.tags())

                # Build overviews
                dst.build_overviews(overview_levels, Resampling.average)
                dst.update_tags(ns="rio_overview", resampling="average")

            logger.info(f"Successfully created COG at {output_path}")
            return True

        except Exception as e:
            logger.error(f"Error creating COG: {str(e)}", exc_info=True)
            return False

    def create_thumbnail(
        self,
        max_size: Tuple[int, int] = (400, 400),
        bands: Optional[Tuple[int, int, int]] = None,
    ) -> Optional[Image.Image]:
        """
        Create a thumbnail from the satellite image
        Uses downsampling during read to avoid memory issues

        Args:
            max_size: Maximum dimensions (width, height)
            bands: Band indices for RGB (e.g., (3, 2, 1) for Landsat true color)

        Returns:
            PIL Image or None
        """
        if not self.src_dataset:
            raise ValueError("Dataset not opened. Use context manager.")

        try:
            # Determine bands to use
            if bands is None:
                if self.src_dataset.count >= 3:
                    bands = (1, 2, 3)  # Default to first three bands
                else:
                    bands = (1,) * 3  # Use first band for grayscale

            # Calculate thumbnail dimensions maintaining aspect ratio
            width_ratio = max_size[0] / self.src_dataset.width
            height_ratio = max_size[1] / self.src_dataset.height
            scale_factor = min(width_ratio, height_ratio)

            thumb_width = int(self.src_dataset.width * scale_factor)
            thumb_height = int(self.src_dataset.height * scale_factor)

            # Read and resample bands using out_shape for memory efficiency
            thumbnail_data = []
            for band_idx in bands:
                if band_idx <= self.src_dataset.count:
                    # Downsample during read
                    data = self.src_dataset.read(
                        band_idx,
                        out_shape=(thumb_height, thumb_width),
                        resampling=Resampling.average,
                    )

                    # Normalize to 0-255
                    data_min = np.nanpercentile(data, 2)
                    data_max = np.nanpercentile(data, 98)
                    data_normalized = np.clip(
                        (data - data_min) / (data_max - data_min) * 255, 0, 255
                    ).astype(np.uint8)

                    thumbnail_data.append(data_normalized)

            # Stack bands
            if len(thumbnail_data) == 3:
                rgb_array = np.stack(thumbnail_data, axis=2)
                thumbnail = Image.fromarray(rgb_array, mode="RGB")
            else:
                thumbnail = Image.fromarray(thumbnail_data[0], mode="L")

            logger.info(f"Created thumbnail with size {thumb_width}x{thumb_height}")
            return thumbnail

        except Exception as e:
            logger.error(f"Error creating thumbnail: {str(e)}")
            return None

    def create_map_overlay_png(
        self,
        max_size: Tuple[int, int] = (2048, 2048),
        bands: Optional[Tuple[int, int, int]] = None,
    ) -> Optional[Image.Image]:
        """
        Create a full-resolution PNG for map overlay display
        Uses downsampling to avoid loading full-resolution bands into memory

        Args:
            max_size: Maximum dimensions (width, height) for the PNG
            bands: Band indices for RGB (e.g., (3, 2, 1) for Landsat true color)

        Returns:
            PIL Image or None
        """
        if not self.src_dataset:
            raise ValueError("Dataset not opened. Use context manager.")

        try:
            # Determine bands to use
            if bands is None:
                if self.src_dataset.count >= 3:
                    bands = (1, 2, 3)  # Default to first three bands
                else:
                    bands = (1,) * 3  # Use first band for grayscale

            # Calculate dimensions, respecting max size but maintaining aspect ratio
            width_ratio = max_size[0] / self.src_dataset.width
            height_ratio = max_size[1] / self.src_dataset.height
            scale_factor = min(width_ratio, height_ratio, 1.0)  # Don't upscale

            png_width = int(self.src_dataset.width * scale_factor)
            png_height = int(self.src_dataset.height * scale_factor)

            logger.info(
                f"Creating map overlay PNG: {png_width}x{png_height} (scale: {scale_factor:.2%})"
            )

            # Read and resample bands using out_shape parameter to downsample during read
            # This avoids loading full-resolution data into memory
            overlay_data = []
            for band_idx in bands:
                if band_idx <= self.src_dataset.count:
                    # Use out_shape to downsample during read - memory efficient
                    data = self.src_dataset.read(
                        band_idx,
                        out_shape=(png_height, png_width),
                        resampling=Resampling.average,
                    )

                    # Normalize to 0-255
                    data_min = np.nanpercentile(data, 2)
                    data_max = np.nanpercentile(data, 98)
                    data_normalized = np.clip(
                        (data - data_min) / (data_max - data_min) * 255, 0, 255
                    ).astype(np.uint8)

                    overlay_data.append(data_normalized)

            # Stack bands
            if len(overlay_data) == 3:
                rgb_array = np.stack(overlay_data, axis=2)
                overlay_png = Image.fromarray(rgb_array, mode="RGB")
            else:
                overlay_png = Image.fromarray(overlay_data[0], mode="L")

            logger.info(f"Created map overlay PNG with size {png_width}x{png_height}")
            return overlay_png

        except Exception as e:
            logger.error(f"Error creating map overlay PNG: {str(e)}")
            return None


def optimize_satellite_image_file(satellite_image_instance) -> bool:
    """
    Optimize a SatelliteImage model instance
    Creates COG and thumbnail, updates model with metadata

    Args:
        satellite_image_instance: SatelliteImage model instance

    Returns:
        bool: True if successful, False otherwise
    """
    from ..models import SatelliteImage

    try:
        logger.info(
            f"Starting optimization for image {satellite_image_instance.id}: {satellite_image_instance.name}"
        )

        # Update status
        satellite_image_instance.status = "processing"
        satellite_image_instance.save(update_fields=["status"])

        input_path = satellite_image_instance.original_image.path
        logger.info(f"Input image path: {input_path}")

        if not os.path.exists(input_path):
            raise Exception(f"Input image file not found: {input_path}")

        with ImageOptimizer(input_path) as optimizer:
            # Extract metadata
            logger.info("Extracting metadata from image...")
            metadata = optimizer.get_image_metadata()
            logger.info(f"Metadata extracted: {metadata}")

            satellite_image_instance.width = metadata["width"]
            satellite_image_instance.height = metadata["height"]
            satellite_image_instance.bands = metadata["bands"]
            satellite_image_instance.resolution = metadata["resolution"][0]
            satellite_image_instance.file_size = os.path.getsize(input_path)

            # Get geographic bounds
            logger.info("Calculating geographic bounds...")
            bounds, center = optimizer.get_geographic_bounds()
            satellite_image_instance.bounds = bounds
            satellite_image_instance.center_point = center
            logger.info(f"Bounds calculated: {bounds}")

            # Create COG
            logger.info("Creating COG (Cloud-Optimized GeoTIFF)...")
            cog_filename = f"cog_{Path(input_path).stem}.tif"
            # Store in the optimized_image upload_to directory with a simpler path
            # Use just the filename, Django will handle the upload_to prefix
            cog_relative_path = cog_filename

            # Get the actual file system path using the field's storage
            storage = satellite_image_instance.optimized_image.storage
            cog_dir_name = "satellite/optimized"  # Match the upload_to prefix

            # Create the full path for writing
            import datetime

            today = datetime.date.today()
            cog_full_dir = os.path.join(
                storage.location, cog_dir_name, str(today.year), f"{today.month:02d}"
            )
            cog_path = os.path.join(cog_full_dir, cog_filename)

            logger.info(f"COG output path: {cog_path}")
            logger.info(
                f"COG directory exists: {os.path.exists(os.path.dirname(cog_path))}"
            )

            if optimizer.create_cog(str(cog_path)):
                # Save COG reference with proper relative path (including year/month)
                relative_path = (
                    f"{cog_dir_name}/{today.year}/{today.month:02d}/{cog_filename}"
                )
                satellite_image_instance.optimized_image.name = relative_path
                logger.info(
                    f"COG created successfully at {cog_path}, relative path: {relative_path}"
                )
            else:
                raise Exception("Failed to create COG")

            # Create thumbnail
            logger.info("Creating thumbnail...")
            thumbnail = optimizer.create_thumbnail()
            if thumbnail:
                thumb_filename = f"thumb_{Path(input_path).stem}.jpg"
                thumb_io = ContentFile(b"")

                # Save thumbnail to BytesIO
                import io

                thumb_buffer = io.BytesIO()
                thumbnail.save(thumb_buffer, format="JPEG", quality=85, optimize=True)
                thumb_buffer.seek(0)

                satellite_image_instance.thumbnail.save(
                    thumb_filename, ContentFile(thumb_buffer.read()), save=False
                )
                logger.info(f"Thumbnail created successfully: {thumb_filename}")

            # Create map overlay PNG
            logger.info("Creating map overlay PNG...")
            overlay_png = optimizer.create_map_overlay_png()
            if overlay_png:
                overlay_filename = f"overlay_{Path(input_path).stem}.png"

                # Save overlay to BytesIO
                import io

                overlay_buffer = io.BytesIO()
                overlay_png.save(overlay_buffer, format="PNG", optimize=True)
                overlay_buffer.seek(0)

                satellite_image_instance.map_overlay.save(
                    overlay_filename, ContentFile(overlay_buffer.read()), save=False
                )
                logger.info(f"Map overlay PNG created successfully: {overlay_filename}")
            else:
                logger.warning("Failed to create map overlay PNG")

        # Update status to optimized
        satellite_image_instance.status = "optimized"
        satellite_image_instance.save()

        logger.info(
            f"Successfully optimized satellite image {satellite_image_instance.id}"
        )
        return True

    except Exception as e:
        logger.error(f"Error optimizing satellite image: {str(e)}", exc_info=True)
        satellite_image_instance.status = "failed"
        satellite_image_instance.processing_error = str(e)
        satellite_image_instance.save(update_fields=["status", "processing_error"])
        return False
