from http3x import App
from http3x.wt import Session

app = App()

class Chat(Session):
    async def on_stream(self, stream):
        async for data in stream:
            await stream.send(data)

app.wt.add('/wt', Chat)

import webbrowser
try:
    webbrowser.open_new_tab(f"{__file__}/../wt_mini.html")
except:
    pass

app.run(host='::', port=4433, certfile="cert.pem", keyfile="key.pem")