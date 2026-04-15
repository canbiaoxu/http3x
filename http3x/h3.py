"""
HTTP/3 module for HTTP3X.

This module provides HTTP/3 request handling classes for HTTP3X.
"""

from ._core.http3 import HTTP3Handler, HTTP3Request

Handler = HTTP3Handler
"""Alias for HTTP3Handler"""

Request = HTTP3Request
"""Alias for HTTP3Request"""