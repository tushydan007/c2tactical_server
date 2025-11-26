#!/usr/bin/env python
import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, '/app')

django.setup()

from satellite.models import SatelliteImage
from satellite.serializers import SatelliteImageListSerializer
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
import json

# Create a fake request
factory = APIRequestFactory()
request = factory.get('/api/satellite/images/')

# Get the image
image = SatelliteImage.objects.first()

if image:
    # Serialize it
    serializer = SatelliteImageListSerializer(image, context={'request': Request(request)})
    print("Serialized data:")
    print(json.dumps(serializer.data, indent=2, default=str))
    
    # Also print the raw bounds
    print("\nRaw bounds from DB:")
    print(f"  bounds: {image.bounds}")
    print(f"  bounds type: {type(image.bounds)}")
    print(f"  get_bounds_coordinates(): {image.get_bounds_coordinates()}")
    
    # And image URLs
    print("\nImage files:")
    print(f"  original_image: {image.original_image}")
    print(f"  optimized_image: {image.optimized_image}")
else:
    print("No images found")
