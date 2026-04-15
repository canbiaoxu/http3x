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