"""
WebTransport module for HTTP3X.

This module provides WebTransport session and stream classes for HTTP3X.
"""

from ._core.webtransport import (
    WebTransportSession, WebTransportStream, WebTransportClient
)

Session = WebTransportSession
"""Alias for WebTransportSession"""

Stream = WebTransportStream
"""Alias for WebTransportStream"""

Client = WebTransportClient
"""Alias for WebTransportClient"""