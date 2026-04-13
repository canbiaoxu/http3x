# HTTP3X

> A WebSocket replacement built on HTTP/3 and QUIC.

Async Python server framework for HTTP/3 + WebTransport (QUIC).

> What WebSocket would look like if it was designed today.

## 🚀 Quick Example

```python
from http3x import App
from http3x.wt import Session

app = App()

class Echo(Session):
    async def on_stream(self, stream):
        async for data in stream:
            await stream.send(data)

app.wt.add("/echo", Echo)
app.run(host='::', port=4433, certfile="cert.pem", keyfile="key.pem")
```

## Installation

```bash
pip install http3x
```

## 🚀 Live Demo

Streaming AI-style responses over HTTP/3 (WebTransport):

```
You: hello

AI:
h
he
hel
hell
hello 👋
```

**This is NOT WebSocket.**  
**This is native HTTP/3 streaming over QUIC.**

![HTTP3X AI Streaming Demo](https://raw.githubusercontent.com/canbiaoxu/http3x/main/demo/wt_demo.png)

See [demo/wt_demo.py](https://github.com/canbiaoxu/http3x/blob/main/demo/wt_demo.py) and [demo/wt_demo.html](https://github.com/canbiaoxu/http3x/blob/main/demo/wt_demo.html) for the complete example.

## ⚡ Why not WebSocket?

| Feature | WebSocket | http3x |
|---------|-----------|--------|
| Protocol | TCP | QUIC (HTTP/3) |
| Streams | Single stream | Multiplexed streams |
| Datagram | No support | Built-in datagram |
| Head-of-line blocking | Yes | No |

## Features

- HTTP/3 server (QUIC-based)
- WebTransport (stream + datagram)
- Multiplexed streams (no head-of-line blocking)
- Async/await API
- Built on aioquic

## Documentation

- [WebTransport Guide](https://github.com/canbiaoxu/http3x/blob/main/docs/webtransport.md) - Complete documentation for WebTransport functionality

More docs coming soon.

## Project Links

- **Source Code**: [GitHub Repository](https://github.com/canbiaoxu/http3x)
- **Documentation**: [https://github.com/canbiaoxu/http3x](https://github.com/canbiaoxu/http3x)
- **PyPI**: [http3x](https://pypi.org/project/http3x)
- **Contributors**: [GitHub Contributors](https://github.com/canbiaoxu/http3x/graphs/contributors)

## Contributing

Contributions are welcome! Please visit the [GitHub repository](https://github.com/canbiaoxu/http3x) to contribute code, report issues, or suggest features.

## License

This project is licensed under the Apache License 2.0. See the [LICENSE](https://github.com/canbiaoxu/http3x/blob/main/LICENSE) file for details.
