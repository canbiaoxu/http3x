from http3x import App
from http3x.wt import Session, Stream
import asyncio

app = App()


async def fake_llm_stream(text: str):
    response = f"Echo: {text} 👋"
    for ch in response:
        await asyncio.sleep(0.05)
        yield ch.encode()


class Chat(Session):
    async def on_stream(self, stream: Stream):
        async for data in stream:
            text = data.decode()
            async for token in fake_llm_stream(text):
                await stream.send(token)


app.wt.add("/chat", Chat)

import webbrowser
try:
    webbrowser.open_new_tab(f"{__file__}/../wt_demo.html")
except:
    pass

app.run(host="::", port=4433, certfile="cert.pem", keyfile="key.pem")
