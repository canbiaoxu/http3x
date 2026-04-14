"""
HTTP3X WebTransport module.

This module contains WebTransport session and stream classes for HTTP3X, including:
- WebTransportStream: Represents a WebTransport stream
- WebTransportSession: Represents a WebTransport session
"""

from __future__ import annotations
import asyncio, logging

from aioquic.h3.events import WebTransportStreamDataReceived

from .base import Signals, QuicConnection, DropQueue


class WebTransportStream:
    """
    Represents a WebTransport stream.
    
    This class provides methods to send and receive data over a WebTransport stream.
    """
    def __init__(self, session: WebTransportSession, stream_id: int):
        """
        Initialize a WebTransportStream.
        
        Args:
            session: The WebTransportSession this stream belongs to
            stream_id: The stream ID
        """
        self.session = session
        self.stream_id = stream_id
        self._stream_msgs: asyncio.Queue[bytes]|DropQueue = asyncio.Queue()
    
    async def send(self, data: bytes, end_stream: bool=False, *, flush=True):
        """
        Send data over the stream.
        
        Args:
            data: The data to send
            end_stream: Whether to end the stream after sending
            flush: Whether to flush the connection after sending
        """
        self.session._conn._quic.send_stream_data(stream_id=self.stream_id, data=data, end_stream=end_stream)
        if flush:
            await self.session.flush()
    
    async def __aiter__(self):
        """
        Asynchronous iterator for receiving data from the stream.
        
        Yields:
            bytes: The received data
        """
        try:
            while True:
                data = await self._stream_msgs.get()
                if type(data) is bytes:
                    yield data
                elif data is Signals.Ended:
                    break
        except Exception as e:
            logging.exception(f"Error in WebTransportStream.__aiter__: {e}")
            self._stream_msgs = DropQueue(maxsize=1)
        else:
            self.session._streams.pop(self.stream_id, None)


class WebTransportSession:
    """
    Represents a WebTransport session.
    
    This class manages WebTransport streams and handles session lifecycle.
    """
    def __init__(
        self,
        *,
        session_id: int,
        connection: QuicConnection,
        remote_addr: tuple[str, int],
        headers: list[tuple[bytes, bytes]],
        raw_path: str,
        path: str,
        path_params: tuple[str],
    ) -> None:
        """
        Initialize a WebTransportSession.
        
        Args:
            session_id: The session ID
            connection: The QuicConnection this session belongs to
            remote_addr: The remote address (host, port)
            headers: The request headers
            raw_path: The full request path
            path: The path without query parameters
            path_params: The path parameters
        """
        self.session_id = session_id
        self.connection = connection
        self.remote_addr = remote_addr
        self.headers = headers
        self.raw_path = raw_path
        self.path = path
        self.path_params = path_params

        self.accepted = False
        self.closed = False
        self._closed_event = asyncio.Event()
        self._event_msgs: asyncio.Queue|DropQueue = asyncio.Queue()
        self._datagram_msgs: asyncio.Queue|DropQueue = asyncio.Queue()
        self._conn = connection._conn
        self._streams: dict[int, WebTransportStream] = {}
    
    async def flush(self):
        """
        Flush the connection.
        
        This sends any pending data over the connection.
        """
        self.connection.transmit()
    
    async def authorize(self) -> bool:
        """
        Authorize the session.
        
        Returns:
            bool: True if authorized, False otherwise
            
        Example:
            ```python
            if dict(self.headers).get(b'authorization') == b'Bearer my-token':
                return True
            else:
                return False
            ```
        """
        return True
    
    async def on_connect(self):
        """
        Called when the session is connected.
        
        This method can be overridden to handle connection events.
        """
        ...

    async def on_close(self):
        """
        Called when the session is closed.
        
        This method can be overridden to handle close events.
        """
        ...
    
    async def on_stream(self, stream: WebTransportStream):
        """
        Called when a new stream is created.
        
        This method can be overridden to handle stream events.
        
        Args:
            stream: The new WebTransportStream
        """
        async for data in stream:
            ...
    
    async def on_datagram(self, data: bytes):
        """
        Called when a datagram is received.
        
        This method can be overridden to handle datagram events.
        
        Args:
            data: The received datagram
        """
        ...

    async def request_close(self):
        """
        Request to close the session.
        """
        self._event_msgs.put_nowait(Signals.Ended)
    
    async def wait_closed(self):
        """
        Wait for the session to close.
        """
        await self._closed_event.wait()
    
    async def send_datagram(self, data: bytes, *, flush=True):
        """
        Send a datagram.
        
        Args:
            data: The datagram to send
            flush: Whether to flush the connection after sending
        """
        self._conn.send_datagram(stream_id=self.session_id, data=data)
        if flush:
            await self.flush()
    
    async def create_stream(self) -> WebTransportStream:
        """
        Create a new bidirectional stream.
        
        Returns:
            WebTransportStream: The new stream
        """
        stream_id = self._conn.create_webtransport_stream(session_id=self.session_id, bidirectional=True)
        stream = self._streams[stream_id] = WebTransportStream(self, stream_id)
        asyncio.create_task(self.on_stream(stream))
        return stream
    
    async def _run(self):
        """
        Run the session.
        
        This method handles session lifecycle and events.
        """
        try:
            self.accepted = bool(await self.authorize())
            if self.accepted:
                try:
                    self._conn.send_headers(stream_id=self.session_id, headers=[(b":status", b"200")])
                    await self.flush()
                    await self.on_connect()
                    asyncio.create_task(self._on_datagram_task())
                    while True:
                        event = await self._event_msgs.get()
                        if isinstance(event, WebTransportStreamDataReceived):
                            stream_id = event.stream_id
                            stream = self._streams.get(stream_id)
                            if not stream:
                                stream = self._streams[stream_id] = WebTransportStream(self, stream_id)
                                asyncio.create_task(self.on_stream(stream))
                            stream._stream_msgs.put_nowait(event.data)
                            if event.stream_ended:
                                stream._stream_msgs.put_nowait(Signals.Ended)
                        elif event is Signals.Ended:
                            break
                finally:
                    self._event_msgs = DropQueue(maxsize=1)
                    self._datagram_msgs.put_nowait(Signals.Ended)
                    for stream_id, stream in list(self._streams.items()):
                        stream._stream_msgs.put_nowait(Signals.Ended)
                        self._streams.pop(stream_id, None)
                    try:
                        await self.flush()
                    except Exception as e:
                        logging.exception(f"Error flushing connection: {e}")
                    self.closed = True
                    self._closed_event.set()
                    await self.wait_closed()
                    await self.on_close()
            else:
                try:
                    self._conn.send_headers(stream_id=self.session_id, headers=[(b":status", b"403")])
                    self._conn.send_data(stream_id=self.session_id, data=b"", end_stream=True)
                    await self.flush()
                finally:
                    self.closed = True
                    self._closed_event.set()
        finally:
            self.closed = True
            self._closed_event.set()
            self.connection._handlers.pop(self.session_id, None)

    async def _on_datagram_task(self):
        """
        Handle datagram events.
        
        This method runs in a separate task to handle datagrams.
        """
        try:
            while True:
                data = await self._datagram_msgs.get()
                if type(data) is bytes:
                    await self.on_datagram(data)
                elif data is Signals.Ended:
                    break
        except Exception as e:
            logging.exception(f"Error in _on_datagram_task: {e}")
            self._datagram_msgs = DropQueue(maxsize=1)