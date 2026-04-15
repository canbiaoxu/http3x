"""
HTTP3X HTTP/3 module.

This module contains HTTP/3 request handling classes for HTTP3X, including:
- HTTP3Request: Represents an HTTP/3 request
- HTTP3Handler: Base class for handling HTTP/3 requests
"""

from __future__ import annotations
import asyncio, logging, json

from aioquic.h3.events import (
    DataReceived, HeadersReceived, DataReceived
)

from .base import (
    Signals, QuicConnection, EndedQueue, Jsonable
)


class HTTP3Request:
    """
    Represents an HTTP/3 request.
    
    This class provides access to request information including headers,
    path, and body data.
    """
    
    def __init__(
        self,
        handler: HTTP3Handler,
        address: tuple[str, int],
        headers: list[tuple[bytes, bytes]],
        raw_path: str,
        path: str,
        path_params: tuple[str],
    ) -> None:
        """
        Initialize an HTTP3Request.
        
        Args:
            handler: The HTTP3Handler handling this request.
            address: The client address (host, port).
            headers: The request headers as a list of (name, value) tuples.
            raw_path: The full request path including query parameters.
            path: The request path without query parameters.
            path_params: The path parameters extracted from the route pattern.
        """
        self.handler = handler
        self.address = address
        self.headers = headers
        self.raw_path = raw_path
        self.path = path
        self.path_params = path_params

    async def body(self):
        """
        Asynchronously iterate over the request body chunks.
        
        Yields:
            bytes: Each chunk of the request body.
        """
        while True:
            chunk = await self.handler._event_msgs.get()
            if type(chunk) is bytes:
                yield chunk
            elif chunk is Signals.Ended:
                break
    
    async def read(self):
        """
        Read the entire request body.
        
        Returns:
            bytes: The complete request body.
        """
        return b''.join([x async for x in self.body()])

class HTTP3Handler:
    """
    Base class for handling HTTP/3 requests.
    
    This class provides methods for handling HTTP/3 requests and sending
    responses. Subclasses should override the get() and post() methods
    to handle GET and POST requests respectively.
    
    Example:
        ```python
        class MyHandler(HTTP3Handler):
            async def get(self):
                await self.write("Hello, World!")
                return "Done"
        ```
    """
    
    def __init__(
        self,
        *,
        session_id: int,
        connection: QuicConnection,

        request_address: tuple[str, int],
        request_headers: list[tuple[bytes, bytes]],
        request_raw_path: str,
        request_path: str,
        request_path_params: tuple[str],
    ) -> None:
        """
        Initialize an HTTP3Handler.
        
        Args:
            session_id: The stream ID for this request.
            connection: The QuicConnection handling this request.
            request_address: The client address (host, port).
            request_headers: The request headers.
            request_raw_path: The full request path including query parameters.
            request_path: The request path without query parameters.
            request_path_params: The path parameters extracted from the route pattern.
        """
        self.session_id = session_id
        self.connection = connection

        self.request = HTTP3Request(
            handler=self,
            address=request_address,
            headers=request_headers,
            raw_path=request_raw_path,
            path=request_path,
            path_params=request_path_params
        )

        self._has_finished = False
        self._closed_event = asyncio.Event()
        self._event_msgs = EndedQueue()
        self._conn = connection._conn
    
    @property
    def closed(self):
        """
        Check if the handler is closed.
        
        Returns:
            bool: True if the handler is closed, False otherwise.
        """
        return self._closed_event.is_set()

    async def write(self, chunk: bytes|str|None|Jsonable, flush=True):
        """
        Write data to the response.
        
        This method sends response headers if not already sent, then sends
        the data chunk. The chunk can be bytes, str, or a JSON-serializable
        object (dict, list, etc.).
        
        Args:
            chunk: The data to write. Can be bytes, str, or a JSON-serializable object.
            flush: Whether to flush the connection after writing.
        """
        assert not self._has_finished
        await self._send_headers()
        if type(chunk) is bytes:
            data = chunk
        elif type(chunk) is str:
            data = chunk.encode('utf-8')
        else:
            data = json.dumps(chunk, ensure_ascii=False).encode('utf-8')
        self._conn.send_data(stream_id=self.session_id, data=data, end_stream=False)
        if flush:
            await self.flush()
    
    async def flush(self):
        """
        Flush the connection.
        
        This sends any pending data over the connection.
        """
        if not self._has_finished:
            self.connection.transmit()

    async def finish(self, chunk: bytes|str|Jsonable=None):
        """
        Finish the response.
        
        This method optionally writes a final chunk and then ends the stream.
        
        Args:
            chunk: Optional final data to write before finishing.
        """
        if chunk is not None:
            assert not self._has_finished
            await self.write(chunk, flush=False)
        if not self._has_finished:
            self._conn.send_data(stream_id=self.session_id, data=b'', end_stream=True)
            await self.flush()
            self._has_finished = True

    async def wait_closed(self):
        """
        Wait for the handler to close.
        """
        await self._closed_event.wait()
    
    async def get(self):
        """
        Handle a GET request.
        
        Override this method in subclasses to handle GET requests.
        
        Returns:
            Optional data to send as the response body.
        """
        pass

    async def post(self):
        """
        Handle a POST request.
        
        Override this method in subclasses to handle POST requests.
        
        Returns:
            Optional data to send as the response body.
        """
        pass
    
    _has_send_headers = False
    _status = 200
    _content_length = 0

    async def _send_headers(self):
        """
        Send response headers.
        
        This method is called automatically by write() if headers haven't
        been sent yet. It sends the status line and default headers.
        """
        if not self._has_send_headers:
            self._has_send_headers = True
            headers = [
                (b":status", str(self._status).encode()),
                (b"content-type", b"text/plain"),
            ]
            if self._content_length:
                headers.append((b"content-length", str(self._content_length).encode()))
            self._conn.send_headers(stream_id = self.session_id, headers = headers, end_stream=False)
            await self.flush()

    async def _run(self):
        """
        Run the handler.
        
        This method is called internally to handle the request lifecycle.
        It dispatches to get() or post() based on the request method.
        """
        try:
            method = dict(self.request.headers).get(b':method')
            if method == b'GET':
                rd = await self.get()
            else:
                assert method == b'POST'
                rd = await self.post()
        except Exception as e:
            try:
                await self.flush()
            except Exception as ef:
                logging.exception(f"Error flushing connection: {ef}")
        else:
            if (rd is not None) or (not self._has_finished):
                await self.finish(rd)
        finally:
            self._event_msgs.close()
            self._closed_event.set()
            self.connection._handlers.pop(self.session_id, None)
