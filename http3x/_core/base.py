"""
HTTP3X core base module.

This module contains the core classes for HTTP3X, including:
- EndedQueue: A queue that drops items when full
- Signals: Signal classes for internal communication
- QuicConnection: QUIC connection protocol implementation
- WebTransportSessionRoutes: WebTransport session route management
- AppConfiguration: Application configuration class
- App: Main application class
"""

from __future__ import annotations
import asyncio, logging, re
from pathlib import Path
from os.path import abspath

from aioquic.asyncio import QuicConnectionProtocol, serve
from aioquic.h3.connection import H3_ALPN, H3Connection, stream_is_unidirectional
from aioquic.h3.events import (
    DatagramReceived,
    H3Event,
    HeadersReceived,
    DataReceived,
    WebTransportStreamDataReceived,
)
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import ProtocolNegotiated, QuicEvent
from aioquic.quic.events import ConnectionTerminated

logging.getLogger("aioquic").setLevel(logging.WARNING)
logging.getLogger("quic").setLevel(logging.WARNING)
logging.getLogger("aioquic.asyncio").setLevel(logging.WARNING)
logging.getLogger("aioquic.asyncio.server").setLevel(logging.WARNING)

Jsonable = str|int|float|bool|list['Jsonable']|dict[str, 'Jsonable']


class EndedQueue(asyncio.Queue):
    """
    A queue that signals when it has been closed.
    
    This queue extends asyncio.Queue to support a 'closed' state. When closed,
    the queue will return Signals.Ended instead of blocking. Items can only
    be added via put_nowait(), not via put() which raises an exception.
    
    This is useful for signaling the end of a stream or session to consumers
    without requiring them to handle cancellation or timeouts.
    """
    
    def __init__(self, maxsize = 0):
        """
        Initialize an EndedQueue.
        
        Args:
            maxsize: Maximum number of items in the queue. 0 means unlimited.
        """
        super().__init__(maxsize)
        self._get_lock = asyncio.Lock()
        self._is_open = True

    async def put(self, item):
        """
        Put an item into the queue asynchronously.
        
        Note:
            This method is intentionally disabled and will always raise an exception.
            Use put_nowait() instead.
            
        Raises:
            Exception: Always raised to prevent async put operations.
        """
        raise

    def put_nowait(self, item):
        """
        Put an item into the queue without blocking.
        
        Items are only accepted while the queue is open. If the queue is closed,
        the item is silently discarded.
        
        Args:
            item: The item to put into the queue.
        """
        if self._is_open:
            super().put_nowait(item)

    async def get(self):
        """
        Get an item from the queue asynchronously.
        
        If the queue is open, this waits for an item to be available.
        If the queue is closed, returns Signals.Ended immediately.
        
        Returns:
            The next item from the queue, or Signals.Ended if closed.
        """
        async with self._get_lock:
            if self._is_open:
                return await super().get()
            else:
                return Signals.Ended

    def get_nowait(self):
        """
        Get an item from the queue without blocking.
        
        If the queue is open and has items, returns the next item.
        If the queue is closed, returns Signals.Ended.
        
        Returns:
            The next item from the queue, or Signals.Ended if closed.
            
        Raises:
            asyncio.QueueEmpty: If the queue is open but empty.
        """
        if self._is_open:
            return super().get_nowait()
        else:
            return Signals.Ended
    
    def close(self):
        """
        Close the queue.
        
        After closing, get() and get_nowait() will return Signals.Ended.
        Any remaining items in the queue are cleared, and a Signals.Ended
        is added to unblock any waiting consumers.
        """
        if self._is_open:
            self._is_open = False
            while not self.empty():
                super().get_nowait()
            super().put_nowait(Signals.Ended)
    
    @property
    def is_open(self):
        """
        Check if the queue is open.
        
        Returns:
            bool: True if the queue is open, False if closed.
        """
        return self._is_open


class Signals:
    """
    Signal classes for internal communication.
    """
    class Ended: 
        """
        Signal indicating that a session or stream has ended.
        """
        ...


class QuicConnection(QuicConnectionProtocol):
    """
    QUIC connection protocol implementation for HTTP3X.
    
    This class handles QUIC events and manages WebTransport sessions.
    """
    _app: 'App'

    def __init__(self, *args, **kwargs):
        """
        Initialize a QuicConnection.
        
        Args:
            *args: Positional arguments for QuicConnectionProtocol
            **kwargs: Keyword arguments for QuicConnectionProtocol
        """
        QuicConnectionProtocol.__init__(self, *args, **kwargs)
        self._handlers: dict[int, WebTransportSession] = {}
        self._conn: H3Connection = None

    def quic_event_received(self, event: QuicEvent):
        """
        Handle QUIC events.
        
        Args:
            event: The QUIC event to handle
        """
        try:
            if isinstance(event, ProtocolNegotiated) and event.alpn_protocol in H3_ALPN:
                self._conn = H3Connection(self._quic, enable_webtransport=True)
            elif isinstance(event, ConnectionTerminated):
                for key, handler in list(self._handlers.items()):
                    handler._event_msgs.close()
                    self._handlers.pop(key, None)
            if self._conn is None: return
            for event in self._conn.handle_event(event):
                event: H3Event
                try:
                    if isinstance(event, HeadersReceived):
                        if (session_id := event.stream_id) in self._handlers: continue
                        headers = dict(event.headers)
                        method = headers.get(b':method')
                        protocol = headers.get(b':protocol')
                        address = self._conn._quic._network_paths[0].addr[:2]
                        raw_path = headers[b':path'].decode('utf-8')
                        path = raw_path.split('?', 1)[0]
                        if method == b"CONNECT":
                            if protocol == b"webtransport" and isinstance(self._conn, H3Connection):
                                for pattern, Handler in self._app.wt.route_patterns.values():
                                    if m := pattern.match(path):
                                        self._handlers[session_id] = handler = Handler(
                                            session_id = session_id,
                                            connection = self,
                                            client_address = address,
                                            client_headers = event.headers,
                                            client_raw_path = raw_path,
                                            client_path = path,
                                            client_path_params = m.groups(),
                                        )
                                        asyncio.create_task(handler._run())
                                        break
                        elif method in (b'GET', b'POST') and not stream_is_unidirectional(event.stream_id):
                            for pattern, Handler in self._app.h3.route_patterns.values():
                                if m := pattern.match(path):
                                    self._handlers[session_id] = handler = Handler(
                                        session_id = session_id,
                                        connection = self,
                                        request_address = address,
                                        request_headers = event.headers,
                                        request_raw_path = raw_path,
                                        request_path = path,
                                        request_path_params = m.groups(),
                                    )
                                    if event.stream_ended:  # no body headers
                                        handler._event_msgs.close()
                                    asyncio.create_task(handler._run())
                                    break
                    elif isinstance(event, DataReceived):  # h3
                        _event_msgs = self._handlers[event.stream_id]._event_msgs
                        _event_msgs.put_nowait(event.data)
                        if event.stream_ended:
                            _event_msgs.close()
                    elif isinstance(event, HeadersReceived):  # h3 tail_headers
                        self._handlers[event.stream_id]._event_msgs.close()
                    elif isinstance(event, DatagramReceived):  # wt
                        self._handlers[event.stream_id]._datagram_msgs.put_nowait(event.data)
                    elif isinstance(event, WebTransportStreamDataReceived):  # wt
                        self._handlers[event.session_id]._event_msgs.put_nowait(event)
                except:
                    pass
        except Exception as e:
            logging.exception(f"Error in quic_event_received: {e}")


class WebTransportSessionRoutes:
    """
    WebTransport session route management.
    
    This class manages routes for WebTransport sessions.
    """
    def __init__(self):
        """
        Initialize WebTransportSessionRoutes.
        """
        self.route_patterns: dict[
            str,
            tuple[
                re.Pattern,
                type[WebTransportSession]
            ]
        ] = {}
 
    def add(self, route_pattern: str, handler: type[WebTransportSession]):
        """
        Add a WebTransport session route.
        
        Args:
            route_pattern: The route pattern to match
            handler: The WebTransportSession class to use for matching routes
        """
        self.route_patterns[route_pattern] = re.compile(route_pattern), handler


class HTTP3Routes:
    """
    HTTP/3 request route management.
    
    This class manages routes for HTTP/3 requests (GET, POST, etc.).
    Routes are matched using regular expressions against the request path.
    """
    
    def __init__(self):
        """
        Initialize HTTP3Routes.
        """
        self.route_patterns: dict[
            str,
            tuple[
                re.Pattern,
                type[HTTP3Handler]
            ]
        ] = {}
 
    def add(self, route_pattern: str, handler: type[HTTP3Handler]):
        """
        Add an HTTP/3 request route.
        
        Args:
            route_pattern: The route pattern to match (regex pattern).
            handler: The HTTP3Handler class to use for matching routes.
        """
        self.route_patterns[route_pattern] = re.compile(route_pattern), handler

class AppConfiguration(QuicConfiguration): 
    """
    Application configuration class.
    
    This class extends QuicConfiguration for HTTP3X applications.
    """
    ...


class App:
    """
    Main application class for HTTP3X.
    
    This class manages WebTransport session routes and server lifecycle.
    """
    def __init__(self):
        """
        Initialize an App instance.
        """
        self.wt = WebTransportSessionRoutes()
        self.h3 = HTTP3Routes()
    
    async def async_run(
                        self,
                        host,
                        port: int,
                        certfile: str|Path,
                        keyfile: str|Path,
                        *,
                        retry: bool=False,
                        configuration: AppConfiguration|None=None,
                        ) -> None:
        """
        Run the application asynchronously.
        
        Args:
            host: The host to listen on
            port: The port to listen on
            certfile: Path to the SSL certificate file
            keyfile: Path to the SSL key file
            retry: Whether to enable QUIC retry
            configuration: Application configuration
        """
        
        class QuicConnection_(QuicConnection):
            _app = self
        
        configuration = configuration or AppConfiguration(
            alpn_protocols=["h3"],
            is_client=False,
        )
        configuration.is_client = False
        configuration.load_cert_chain(
            abspath(str(certfile)), abspath(str(keyfile))
        )
        self.server = await serve(
            host = host,
            port = port,
            configuration = configuration,
            create_protocol = QuicConnection_,
            retry = retry,
        )
        print(f"http3x running on https://{host}:{port}")
    
    def run(
            self,
            host,
            port: int,
            certfile: str|Path,
            keyfile: str|Path,
            *,
            retry: bool=False,
            configuration: AppConfiguration|None=None,
            ) -> None:
        """
        Run the application synchronously.
        
        Args:
            host: The host to listen on
            port: The port to listen on
            certfile: Path to the SSL certificate file
            keyfile: Path to the SSL key file
            retry: Whether to enable QUIC retry
            configuration: Application configuration
        """
        
        async def run_forever():
            await self.async_run(
                host,
                port,
                certfile,
                keyfile,
                retry = retry,
                configuration = configuration,
            )
            await asyncio.Event().wait()
        asyncio.run(run_forever())
    
    def close(self):
        """
        Close the server.
        """
        self.server.close()
        print(f"Http3x server have closed")

# Put it at the bottom to avoid circular imports:

from .webtransport import WebTransportSession
from .http3 import HTTP3Handler
