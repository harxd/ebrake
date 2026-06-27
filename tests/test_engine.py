import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from app.engine import get_vmaf_model_filter_param

def test_vmaf_model_selection():
    # Test explicitly selected models (ignore resolution)
    assert "vmaf_4k" not in get_vmaf_model_filter_param("1080p", 3840, 2160)
    assert "vmaf_4k" not in get_vmaf_model_filter_param("4k_far", 3840, 2160)
    assert "vmaf_4k_v0.6.1" in get_vmaf_model_filter_param("4k_near", 1920, 1080)
    
    # Test Auto Near logic
    # 1080p input -> should pick 1080p model
    assert "vmaf_4k" not in get_vmaf_model_filter_param("auto_near", 1920, 1080)
    # 4K input -> should pick 4k_near model
    assert "vmaf_4k_v0.6.1" in get_vmaf_model_filter_param("auto_near", 3840, 2160)
    
    # Test Auto Far logic
    # 1080p input -> should pick 1080p model
    assert "vmaf_4k" not in get_vmaf_model_filter_param("auto_far", 1920, 1080)
    # 4K input -> should pick 4k_far (which is functionally equivalent to the 1080p model file, vmaf_v0.6.1)
    assert "vmaf_4k" not in get_vmaf_model_filter_param("auto_far", 3840, 2160)
