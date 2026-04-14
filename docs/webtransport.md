# WebTransport

WebTransport is a modern protocol that provides low-latency, bidirectional communication between clients and servers. It is built on top of HTTP/3 and QUIC, offering both datagram and stream-based communication.

## Overview

HTTP3X provides a simple and intuitive API for building WebTransport servers. The framework handles the underlying QUIC and HTTP/3 protocols, allowing you to focus on your application logic.

### Key Features

- **Bidirectional Streams**: Reliable, ordered data streams for streaming data
- **Datagrams**: Unreliable, unordered messages for low-latency communication
- **Async/Await Support**: Native Python async/await syntax for handling connections
- **Route-based Handlers**: Organize your WebTransport endpoints with route patterns
- **Easy Integration**: Simple API that integrates with the HTTP3X application

## Installation

```bash
pip install http3x
```

## Quick Start

### Server-Side

```python
from http3x import App
from http3x.wt import Session, Stream

app = App()

class Chat(Session):
    async def on_stream(self, stream: Stream):
        async for data in stream:
            await stream.send(data)

app.wt.add('/wt', Chat)

app.run(host='::', port=4433, certfile="cert.pem", keyfile="key.pem")
```

### Client-Side (JavaScript)

```javascript
const transport = new WebTransport("https://localhost:4433/wt", { allowInsecure: true });
await transport.ready;

// Send a datagram
const writer = transport.datagrams.writable.getWriter();
await writer.write(new TextEncoder().encode("Hello!"));

// Create a bidirectional stream
const stream = await transport.createBidirectionalStream();
const streamWriter = stream.writable.getWriter();
await streamWriter.write(new TextEncoder().encode("Stream message"));
```

## Session Class

The `Session` class (alias for `WebTransportSession`) is the main class for handling WebTransport connections. You create a subclass and override its methods to handle various events.

### Session Properties

| Property | Type | Description |
|----------|------|-------------|
| `session_id` | `int` | The unique identifier for this session |
| `connection` | `QuicConnection` | The underlying QUIC connection |
| `remote_addr` | `tuple[str, int]` | The remote address (host, port) |
| `headers` | `list[tuple[bytes, bytes]]` | The request headers from the client |
| `raw_path` | `str` | The full request path including query parameters |
| `path` | `str` | The path without query parameters |
| `path_params` | `tuple[str]` | Captured path parameters from route pattern |
| `accepted` | `bool` | Whether the session was accepted |
| `closed` | `bool` | Whether the session is closed |

### Session Methods to Override

#### `authorize() -> bool`

Called to determine if the session should be accepted. Override this method to implement custom authorization logic.

```python
class MySession(Session):
    async def authorize(self) -> bool:
        headers_dict = dict(self.headers)
        auth_header = headers_dict.get(b'authorization', b'')
        return auth_header == b'Bearer my-secret-token'
```

**Returns**: `True` to accept the session, `False` to reject with a 403 response.

---

#### `on_connect()`

Called when the session is successfully connected. Use this to perform initialization tasks.

```python
class MySession(Session):
    async def on_connect(self):
        print(f"Client connected from {self.remote_addr}")
        await self.send_datagram(b'Welcome!')
```

---

#### `on_close()`

Called when the session is closed. Use this for cleanup tasks.

```python
class MySession(Session):
    async def on_close(self):
        print(f"Session {self.session_id} closed")
```

---

#### `on_stream(stream: Stream)`

Called when a new stream is created by the client or when you create a stream server-side. The stream is an async iterator that yields received data.

```python
class MySession(Session):
    async def on_stream(self, stream: Stream):
        async for data in stream:
            processed = data.upper()
            await stream.send(processed)
```

---

#### `on_datagram(data: bytes)`

Called when a datagram is received from the client.

```python
class MySession(Session):
    async def on_datagram(self, data: bytes):
        print(f"Received datagram: {data}")
        await self.send_datagram(b'Echo: ' + data)
```

### Session Methods to Call

#### `send_datagram(data: bytes, *, flush: bool = True)`

Send a datagram to the client.

```python
await self.send_datagram(b'Hello, client!')
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data` | `bytes` | required | The data to send |
| `flush` | `bool` | `True` | Whether to flush the connection immediately |

---

#### `create_stream() -> Stream`

Create a new bidirectional stream from the server side.

```python
stream = await self.create_stream()
await stream.send(b'Server-initiated message')
```

**Returns**: A new `Stream` instance.

---

#### `request_close()`

Request to close the session gracefully.

```python
await self.request_close()
```

---

#### `wait_closed()`

Wait until the session is closed.

```python
await self.wait_closed()
```

---

#### `flush()`

Flush any pending data to the connection.

```python
await self.flush()
```

## Stream Class

The `Stream` class (alias for `WebTransportStream`) represents a bidirectional WebTransport stream.

### Stream Properties

| Property | Type | Description |
|----------|------|-------------|
| `session` | `Session` | The session this stream belongs to |
| `stream_id` | `int` | The unique identifier for this stream |

### Stream Methods

#### `send(data: bytes, end_stream: bool = False, *, flush: bool = True)`

Send data over the stream.

```python
await stream.send(b'Hello!')
await stream.send(b'Goodbye!', end_stream=True)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data` | `bytes` | required | The data to send |
| `end_stream` | `bool` | `False` | Whether to end the stream after sending |
| `flush` | `bool` | `True` | Whether to flush the connection immediately |

### Stream Async Iterator

The stream is an async iterator that yields received data:

```python
async for data in stream:
    print(f"Received: {data}")
    await stream.send(b'Acknowledged')
```

## Routing

WebTransport sessions are routed using path patterns. The framework supports regex-based route matching.

### Basic Routing

```python
app.wt.add('/chat', ChatSession)
app.wt.add('/game', GameSession)
```

### Path Parameters

Use regex capture groups to extract path parameters:

```python
class RoomSession(Session):
    async def on_connect(self):
        room_id = self.path_params[0]
        print(f"Joined room: {room_id}")

app.wt.add(r'/room/(\w+)', RoomSession)
```

The captured groups are available in `self.path_params` as a tuple.

## Running the Server

### Synchronous

```python
app.run(
    host='::',
    port=4433,
    certfile="cert.pem",
    keyfile="key.pem"
)
```

### Asynchronous

```python
async def main():
    await app.async_run(
        host='::',
        port=4433,
        certfile="cert.pem",
        keyfile="key.pem"
    )
    await asyncio.Event().wait()

asyncio.run(main())
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | `str` | required | The host to bind to (`'::'` for all interfaces) |
| `port` | `int` | required | The port to listen on |
| `certfile` | `str \| Path` | required | Path to the SSL certificate file |
| `keyfile` | `str \| Path` | required | Path to the SSL private key file |
| `retry` | `bool` | `False` | Enable QUIC retry mechanism |
| `configuration` | `AppConfiguration \| None` | `None` | Custom QUIC configuration |

## SSL Certificates

WebTransport requires HTTPS. You can generate a self-signed certificate for development using mkcert:

```bash
mkcert -cert-file cert.pem -key-file key.pem localhost 127.0.0.1 ::1
```

For production, use a certificate from a trusted Certificate Authority.

## Complete Example

### Server (Python)

```python
from http3x import App
from http3x.wt import Session, Stream

app = App()

class Chat(Session):
    async def authorize(self) -> bool:
        headers_dict = dict(self.headers)
        token = headers_dict.get(b'authorization', b'')
        return token == b'Bearer secret-token'
    
    async def on_connect(self):
        await self.send_datagram(b'Welcome to the chat!')
    
    async def on_close(self):
        print(f'Session closed: {self.session_id}')
    
    async def on_stream(self, stream: Stream):
        async for data in stream:
            await stream.send(b'Echo: ' + data)
    
    async def on_datagram(self, data: bytes):
        await self.send_datagram(b'Datagram echo: ' + data)

app.wt.add('/chat', Chat)

app.run(host='::', port=4433, certfile="cert.pem", keyfile="key.pem")
```

### Client (HTML/JavaScript)

```html
<!DOCTYPE html>
<html>
<head>
  <title>WebTransport Client</title>
</head>
<body>
  <script>
    (async () => {
      const transport = new WebTransport("https://localhost:4433/chat", { allowInsecure: true });
      
      await transport.ready;
      console.log("Connected!");

      // Handle datagrams
      const dgReader = transport.datagrams.readable.getReader();
      (async () => {
        while (true) {
          const { value, done } = await dgReader.read();
          if (done) break;
          console.log("Datagram:", new TextDecoder().decode(value));
        }
      })();

      // Send a datagram
      const dgWriter = transport.datagrams.writable.getWriter();
      await dgWriter.write(new TextEncoder().encode("Hello!"));

      // Create a stream
      const stream = await transport.createBidirectionalStream();
      const streamWriter = stream.writable.getWriter();
      await streamWriter.write(new TextEncoder().encode("Stream message"));

      // Read stream response
      const streamReader = stream.readable.getReader();
      const { value } = await streamReader.read();
      console.log("Stream response:", new TextDecoder().decode(value));
    })();
  </script>
</body>
</html>
```

## Browser Support

WebTransport is supported in modern browsers:

- Chrome 97+
- Edge 97+
- Opera 83+

Check current browser support at [caniuse.com/webtransport](https://caniuse.com/webtransport).

## Error Handling

The framework handles errors gracefully. Sessions are automatically cleaned up when:

- The client disconnects
- The connection times out
- An unhandled exception occurs

You can add error handling in your session methods:

```python
class MySession(Session):
    async def on_stream(self, stream: Stream):
        try:
            async for data in stream:
                try:
                    await stream.send(process(data))
                except Exception as e:
                    await stream.send(b'Error processing data')
        except Exception as e:
            print(f"Stream error: {e}")
```

## Performance Tips

1. **Use Datagrams for Low Latency**: Datagrams are faster but unreliable. Use them for real-time data where occasional packet loss is acceptable.

2. **Use Streams for Reliability**: Streams provide ordered, reliable delivery. Use them for important data that must arrive intact.

3. **Batch Operations**: Set `flush=False` when sending multiple messages, then call `flush()` once:

   ```python
   await stream.send(b'part1', flush=False)
   await stream.send(b'part2', flush=False)
   await stream.send(b'part3', flush=True)
   ```

4. **Handle Backpressure**: The async iterator naturally handles backpressure. Don't buffer more data than necessary.

## API Reference

### Imports

```python
from http3x import App, AppConfiguration
from http3x.wt import Session, Stream
```

### App

Main application class for HTTP3X.

| Method | Description |
|--------|-------------|
| `wt.add(pattern, handler)` | Register a WebTransport session handler |
| `run(...)` | Run the server synchronously |
| `async_run(...)` | Run the server asynchronously |
| `close()` | Close the server |

### Session

Base class for WebTransport session handlers.

| Method | Description |
|--------|-------------|
| `authorize()` | Override to implement authorization |
| `on_connect()` | Called when session connects |
| `on_close()` | Called when session closes |
| `on_stream(stream)` | Called for each stream |
| `on_datagram(data)` | Called for each datagram |
| `send_datagram(data)` | Send a datagram |
| `create_stream()` | Create a new stream |
| `request_close()` | Request session close |
| `wait_closed()` | Wait for session to close |
| `flush()` | Flush pending data |

### Stream

Represents a WebTransport stream.

| Method | Description |
|--------|-------------|
| `send(data, end_stream=False)` | Send data over the stream |
| `async for data in stream` | Iterate over received data |
