"""
HTTP3X WebTransport module.

This module contains WebTransport session and stream classes for HTTP3X, including:
- WebTransportStream: Represents a WebTransport stream
- WebTransportSession: Represents a WebTransport session
"""

from __future__ import annotations
import asyncio, logging

from aioquic.h3.events import WebTransportStreamDataReceived

from .base import Signals, QuicConnection, EndedQueue


class WebTransportStreamClosedError(Exception):
    """
    Exception raised when attempting to operate on a closed WebTransport stream.
    """
    ...


class WebTransportStream:
    """
    Represents a WebTransport stream.
    
    This class provides methods to send and receive data over a WebTransport stream.
    """
    def __init__(self, session: WebTransportSession, stream_id: int, can_send: bool, can_recv: bool):
        """
        Initialize a WebTransportStream.
        
        Args:
            session: The WebTransportSession this stream belongs to
            stream_id: The stream ID
        """
        self.session = session
        self.stream_id = stream_id
        self.can_send = can_send
        self.can_recv = can_recv
        self._stream_msgs: EndedQueue = EndedQueue()
    
    @property
    def closed(self):
        """
        Check if the stream is closed.
        
        A stream is closed when it can neither send nor receive data.
        
        Returns:
            bool: True if the stream is closed, False otherwise.
        """
        return not (self.can_send or self.can_recv)
    
    async def send(self, data: bytes, end_stream: bool=False, *, flush=True):
        """
        Send data over the stream.
        
        Args:
            data: The data to send
            end_stream: Whether to end the stream after sending
            flush: Whether to flush the connection after sending
        """
        if not self.can_send:
            raise WebTransportStreamClosedError()
        self.session._conn._quic.send_stream_data(stream_id=self.stream_id, data=data, end_stream=end_stream)
        if flush:
            await self.session.flush()
        if end_stream:
            self.can_send = False
            if not self.can_recv:
                self.session._streams.pop(self.stream_id, None)

    def close(self, error_code: int):
        """
        Close the stream with an error code.
        
        This resets the stream and marks it as closed for both sending and receiving.
        
        Args:
            error_code: The error code to send when resetting the stream.
        """
        self.session._conn._quic.reset_stream(self.stream_id, error_code)
        self._stream_msgs.close()
        self.can_recv = False
        self.can_send = False
        self.session._streams.pop(self.stream_id, None)

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
        finally:
            self._stream_msgs.close()
            self.can_recv = False
            if not self.can_send:
                self.session._streams.pop(self.stream_id, None)


class WebTransportClient:
    """
    Represents a WebTransport client connection.
    
    This class provides information about the client that connected to the server.
    """
    
    def __init__(
        self,
        address: tuple[str, int],
        headers: list[tuple[bytes, bytes]],
        raw_path: str,
        path: str,
        path_params: tuple[str],
    ) -> None:
        """
        Initialize a WebTransportClient.
        
        Args:
            address: The remote address (host, port)
            headers: The request headers
            raw_path: The full request path
            path: The path without query parameters
            path_params: The path parameters
        """
        self.address = address
        self.headers = headers
        self.raw_path = raw_path
        self.path = path
        self.path_params = path_params

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

        client_address: tuple[str, int],
        client_headers: list[tuple[bytes, bytes]],
        client_raw_path: str,
        client_path: str,
        client_path_params: tuple[str],
    ) -> None:
        """
        Initialize a WebTransportSession.
        
        Args:
            session_id: The session ID
            connection: The QuicConnection this session belongs to
            client_address: The remote address (host, port)
            client_headers: The request headers
            client_raw_path: The full request path
            client_path: The path without query parameters
            client_path_params: The path parameters
        """
        self.session_id = session_id
        self.connection = connection

        self.client = WebTransportClient(
            address=client_address,
            headers=client_headers,
            raw_path=client_raw_path,
            path=client_path,
            path_params=client_path_params
        )

        self.accepted = False
        self._closed_event = asyncio.Event()
        self._event_msgs = EndedQueue()
        self._datagram_msgs = EndedQueue()
        self._conn = connection._conn
        self._streams: dict[int, WebTransportStream] = {}
        self._async_tasks = []
    
    @property
    def closed(self):
        """
        Check if the session is closed.
        
        Returns:
            bool: True if the session is closed, False otherwise.
        """
        return self._closed_event.is_set()
    
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
            if dict(self.client.headers).get(b'authorization') == b'Bearer my-token':
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
    
    async def create_stream(self, can_recv: bool=True) -> WebTransportStream:
        """
        Create a new WebTransport stream.
        
        Args:
            can_recv: Whether the stream can receive data. If True, creates
                a bidirectional stream; if False, creates a unidirectional stream.
        
        Returns:
            WebTransportStream: The newly created stream.
        """
        stream_id = self._conn.create_webtransport_stream(session_id=self.session_id, is_unidirectional=not can_recv)
        stream = WebTransportStream(self, stream_id, can_send=True, can_recv=can_recv)
        self._streams[stream_id] = stream
        if can_recv:
            asyncio.create_task(self.on_stream(stream))
        return stream
    
    def close(self):
        """
        Close the session.
        
        This closes all streams and signals that the session has ended.
        """
        self._event_msgs.close()
        self._datagram_msgs.close()
        self._closed_event.set()
        try:
            self._conn._quic.reset_stream(self.session_id, 0)
            self.connection.transmit()
        except Exception:
            pass
    
    async def _run(self):
        """
        Run the session.
        
        This method handles session lifecycle and events.
        """
        try:
            self.accepted = bool(await self.authorize())
        except:
            self._event_msgs.close()
            self._datagram_msgs.close()
            self._closed_event.set()
            try:
                self._conn._quic.reset_stream(self.session_id, 0)
                self.connection.transmit()
            except Exception:
                pass
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
                            can_send = ((stream_id & 0x2) == 0) or ((stream_id & 0x1) != 0)
                            stream = WebTransportStream(self, stream_id, can_send=can_send, can_recv=True)
                            self._streams[stream_id] = stream
                            asyncio.create_task(self.on_stream(stream))
                        stream._stream_msgs.put_nowait(event.data)
                        if event.stream_ended:
                            stream.can_recv = False
                            stream._stream_msgs.close()
                            if stream.closed:
                                self._streams.pop(stream_id, None)
                    elif event is Signals.Ended:
                        break
            finally:
                self._event_msgs.close()
                self._datagram_msgs.close()
                for stream_id, stream in list(self._streams.items()):
                    stream._stream_msgs.close()
                    stream.can_recv = False
                    stream.can_send = False
                    self._streams.pop(stream_id, None)
                try:
                    await self.flush()
                except Exception as e:
                    pass
                self._closed_event.set()
                self.connection._handlers.pop(self.session_id, None)
                await self.on_close()
        else:
            try:
                self._conn.send_headers(stream_id=self.session_id, headers=[(b":status", b"403")])
                self._conn.send_data(stream_id=self.session_id, data=b"", end_stream=True)
                self._conn._quic.reset_stream(self.session_id, 0)
            finally:
                try:
                    await self.flush()
                except:
                    pass
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
            self._datagram_msgs.close()