# HTTP/3

HTTP/3 is the third major version of the Hypertext Transfer Protocol, built on top of QUIC. It provides faster connection establishment, improved performance over lossy networks, and multiplexed streams without head-of-line blocking.

## Overview

HTTP3X provides a simple and intuitive API for building HTTP/3 servers. The framework handles the underlying QUIC protocol, allowing you to focus on your application logic.

### Key Features

- **HTTP/3 Server**: Built on QUIC for improved performance
- **Async/Await Support**: Native Python async/await syntax for handling requests
- **Route-based Handlers**: Organize your HTTP/3 endpoints with route patterns
- **Easy Integration**: Simple API that integrates with the HTTP3X application
- **Streaming Support**: Efficiently handle large requests and responses

## Installation

```bash
pip install http3x
```

## Quick Start

### Server-Side

```python
from http3x import App
from http3x.h3 import Handler

app = App()

class ApiHandler(Handler):
    async def get(self):
        return {'status': 'ok'}
    
    async def post(self):
        return {'status': 'ok'}

app.h3.add('/h3', ApiHandler)

app.run(host='0.0.0.0', port=443, certfile="cert.pem", keyfile="key.pem")
```

### Client-Side

Using curl with HTTP/3 support:

```bash
curl --http3-only -k https://localhost:443/h3
curl --http3-only -k -X POST -d "Hello, HTTP/3!" https://localhost:443/h3
```

## Handler Class

The `Handler` class (alias for `HTTP3Handler`) is the main class for handling HTTP/3 requests. You create a subclass and override its methods to handle GET and POST requests.

### Handler Properties

| Property | Type | Description |
|----------|------|-------------|
| `session_id` | `int` | The unique identifier for this request stream |
| `connection` | `QuicConnection` | The underlying QUIC connection |
| `request` | `HTTP3Request` | The request object containing request information |
| `request.address` | `tuple[str, int]` | The client address (host, port) |
| `request.headers` | `list[tuple[bytes, bytes]]` | The request headers |
| `request.raw_path` | `str` | The full request path including query parameters |
| `request.path` | `str` | The path without query parameters |
| `request.path_params` | `tuple[str]` | Captured path parameters from route pattern |
| `closed` | `bool` | Whether the handler is closed |

### Handler Methods to Override

#### `get()`

Called to handle GET requests. Override this method to implement custom GET request handling.

```python
class MyHandler(Handler):
    async def get(self):
        await self.write("Hello, World!")
        return "Done"
```

**Returns**: Optional data to send as the response body.

---

#### `post()`

Called to handle POST requests. Override this method to implement custom POST request handling.

```python
class MyHandler(Handler):
    async def post(self):
        body = await self.request.read()
        return {"received": body.decode()}
```

**Returns**: Optional data to send as the response body.

### Handler Methods to Call

#### `write(chunk, flush=True)`

Write data to the response. This method sends response headers if not already sent, then sends the data chunk.

```python
await self.write("Hello!")
await self.write({"status": "ok"})  # JSON serialization
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `chunk` | `bytes  str  Jsonable` | required | The data to write |
| `flush` | `bool` | `True` | Whether to flush the connection immediately |

---

#### `finish(chunk=None)`

Finish the response. This method optionally writes a final chunk and then ends the stream.

```python
await self.finish("Goodbye!")
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `chunk` | `bytes  str  Jsonable` | `None` | Optional final data to write |

---

#### `flush()`

Flush any pending data to the connection.

```python
await self.flush()
```

---

#### `wait_closed()`

Wait until the handler is closed.

```python
await self.wait_closed()
```

## Request Class

The `Request` class (alias for `HTTP3Request`) represents an HTTP/3 request and provides access to request information.

### Request Properties

| Property | Type | Description |
|----------|------|-------------|
| `handler` | `HTTP3Handler` | The handler handling this request |
| `address` | `tuple[str, int]` | The client address (host, port) |
| `headers` | `list[tuple[bytes, bytes]]` | The request headers |
| `raw_path` | `str` | The full request path including query parameters |
| `path` | `str` | The path without query parameters |
| `path_params` | `tuple[str]` | Captured path parameters from route pattern |

### Request Methods

#### `body()`

Asynchronously iterate over the request body chunks.

```python
async for chunk in self.request.body():
    process_chunk(chunk)
```

**Yields**: `bytes` - Each chunk of the request body.

---

#### `read()`

Read the entire request body.

```python
body = await self.request.read()
print(body.decode())
```

**Returns**: `bytes` - The complete request body.

## Routing

HTTP/3 requests are routed using path patterns. The framework supports regex-based route matching.

### Basic Routing

```python
app.h3.add('/api', ApiHandler)
app.h3.add('/docs', DocsHandler)
```

### Path Parameters

Use regex capture groups to extract path parameters:

```python
class UserHandler(Handler):
    async def get(self):
        user_id = self.request.path_params[0]
        return {"user_id": user_id}

app.h3.add(r'/user/(\d+)', UserHandler)
```

The captured groups are available in `self.request.path_params` as a tuple.

## Running the Server

### Synchronous

```python
app.run(
    host='0.0.0.0',
    port=443,
    certfile="cert.pem",
    keyfile="key.pem"
)
```

### Asynchronous

```python
async def main():
    await app.async_run(
        host='0.0.0.0',
        port=443,
        certfile="cert.pem",
        keyfile="key.pem"
    )
    await asyncio.Event().wait()

asyncio.run(main())
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | `str` | required | The host to bind to (`'0.0.0.0'` for all interfaces) |
| `port` | `int` | required | The port to listen on |
| `certfile` | `str \| Path` | required | Path to the SSL certificate file |
| `keyfile` | `str \| Path` | required | Path to the SSL private key file |
| `retry` | `bool` | `False` | Enable QUIC retry mechanism |
| `configuration` | `AppConfiguration \| None` | `None` | Custom QUIC configuration |

## SSL Certificates

HTTP/3 requires HTTPS. You can generate a self-signed certificate for development using mkcert:

```bash
mkcert -cert-file cert.pem -key-file key.pem localhost 127.0.0.1 ::1
```

For production, use a certificate from a trusted Certificate Authority.

## Complete Example

### Server (Python)

```python
from http3x import App
from http3x.h3 import Handler

app = App()

class ApiHandler(Handler):
    async def get(self):
        return {
            "message": "Hello, HTTP/3!",
            "method": "GET"
        }
    
    async def post(self):
        body = await self.request.read()
        return {
            "message": "Received POST data",
            "data": body.decode()
        }

app.h3.add('/api', ApiHandler)

class UserHandler(Handler):
    async def get(self):
        user_id = self.request.path_params[0]
        return {
            "user_id": user_id,
            "name": f"User {user_id}"
        }

app.h3.add(r'/user/(\d+)', UserHandler)

app.run(host='0.0.0.0', port=443, certfile="cert.pem", keyfile="key.pem")
```

### Client (curl)

```bash
# Test GET request
curl --http3-only -k https://localhost:443/api

# Test POST request
curl --http3-only -k -X POST -d "Hello, HTTP/3!" https://localhost:443/api

# Test path parameters
curl --http3-only -k https://localhost:443/user/123
```

## Error Handling

The framework handles errors gracefully. Requests are automatically cleaned up when:

- The client disconnects
- The connection times out
- An unhandled exception occurs

You can add error handling in your handler methods:

```python
class MyHandler(Handler):
    async def get(self):
        try:
            # Your logic here
            return {"status": "ok"}
        except Exception as e:
            # Handle error
            await self.write({"error": str(e)})
            return
```

## Performance Tips

1. **Use Streaming for Large Data**: For large request or response bodies, use the streaming API to avoid loading everything into memory.

2. **Batch Operations**: Set `flush=False` when sending multiple messages, then call `flush()` once:

   ```python
   await self.write(b'part1', flush=False)
   await self.write(b'part2', flush=False)
   await self.write(b'part3', flush=True)
   ```

3. **Handle Backpressure**: The async API naturally handles backpressure. Don't buffer more data than necessary.

## API Reference

### Imports

```python
from http3x import App, AppConfiguration
from http3x.h3 import Handler, Request
```

### App

Main application class for HTTP3X.

| Method | Description |
|--------|-------------|
| `h3.add(pattern, handler)` | Register an HTTP/3 request handler |
| `run(...)` | Run the server synchronously |
| `async_run(...)` | Run the server asynchronously |
| `close()` | Close the server |

### Handler

Base class for HTTP/3 request handlers.

| Method | Description |
|--------|-------------|
| `get()` | Handle GET requests |
| `post()` | Handle POST requests |
| `write(data)` | Write data to the response |
| `finish(data)` | Finish the response |
| `flush()` | Flush pending data |
| `wait_closed()` | Wait for handler to close |

### Request

Represents an HTTP/3 request.

| Method | Description |
|--------|-------------|
| `body()` | Asynchronously iterate over request body chunks |
| `read()` | Read the entire request body |