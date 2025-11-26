#!/usr/bin/env python
import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, '/app')

django.setup()

from satellite.models import SatelliteImage

for img in SatelliteImage.objects.all():
    print(f"\nImage: {img.name} (ID: {img.id})")
    print(f"  Status: {img.status}")
    print(f"  Optimized image: {img.optimized_image}")
    print(f"  Original image: {img.original_image}")
    print(f"  Bounds (raw): {img.bounds}")
    print(f"  Bounds (coords): {img.get_bounds_coordinates()}")
    print(f"  Center point: {img.center_point}")
