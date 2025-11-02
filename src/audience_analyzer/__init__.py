"""Audience Analyzer Module

Expose core analyzers. The visual analyzer depends on OpenCV (cv2) and is
intentionally not imported at package import time to avoid optional binary
dependency issues during API startup. Import it directly from
``audience_analyzer.visual_analyzer`` if needed.
"""

from .analyzer import AudienceAnalyzer
from .realtime_analyzer import RealtimeAudienceAnalyzer

__all__ = ['AudienceAnalyzer', 'RealtimeAudienceAnalyzer']
