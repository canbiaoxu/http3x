"""
HTTP3X core base module.

This module contains the core classes for HTTP3X, including:
- DropQueue: A queue that drops items when full
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
from aioquic.h3.connection import H3_ALPN, H3Connection
from aioquic.h3.events import (
    DatagramReceived,
    H3Event,
    HeadersReceived,
    WebTransportStreamDataReceived,
)
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import ProtocolNegotiated, QuicEvent
from aioquic.quic.events import ConnectionTerminated

logging.getLogger("aioquic").setLevel(logging.WARNING)
logging.getLogger("quic").setLevel(logging.WARNING)
logging.getLogger("aioquic.asyncio").setLevel(logging.WARNING)
logging.getLogger("aioquic.asyncio.server").setLevel(logging.WARNING)


class DropQueue(asyncio.Queue):
    """
    A queue that drops items when full.
    
    This is used to prevent queue overflow in high-traffic scenarios.
    """
    def put_nowait(self, item):
        """
        Put an item into the queue without waiting.
        
        If the queue is full, the item is dropped.
        
        Args:
            item: The item to put into the queue
        """
        try:
            asyncio.Queue.put_nowait(self, item)
        except asyncio.queues.QueueFull:
            pass


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
                    handler._event_msgs.put_nowait(Signals.Ended)
                    self._handlers.pop(key, None)
            if self._conn is not None:
                for event in self._conn.handle_event(event):
                    event: H3Event
                    try:
                        if isinstance(event, HeadersReceived):
                            if (session_id := event.stream_id) in self._handlers: continue
                            if not isinstance(self._conn, H3Connection): continue
                            headers = dict(event.headers)
                            if not (headers[b':method'] == b"CONNECT" and headers[b':protocol'] == b"webtransport"): continue
                            address = self._conn._quic._network_paths[0].addr[:2]
                            raw_path = headers[b':path'].decode('utf-8')
                            path = raw_path.split('?', 1)[0]
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
                        elif isinstance(event, DatagramReceived):
                            self._handlers[event.stream_id]._datagram_msgs.put_nowait(event.data)
                        elif isinstance(event, WebTransportStreamDataReceived):
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
        configuration.load_cert_chain(abspath(str(certfile)), abspath(str(keyfile)))
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
            await self.async_run(host, port, certfile, keyfile, retry=retry, configuration=configuration)
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
