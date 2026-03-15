"""
Minimal webhook receiver signature verification example.

Run:
  python scripts_webhook_verify_example.py
Then expose with ngrok/cloudflared if needed.
"""

import hmac
import json
from hashlib import sha256

from fastapi import FastAPI, Header, HTTPException, Request
import uvicorn

app = FastAPI()
WEBHOOK_SECRET = 'whsec_xxx'


@app.post('/webhooks/jobspy')
async def receive(
    request: Request,
    x_webhook_timestamp: str = Header(...),
    x_webhook_signature: str = Header(...),
):
    body_bytes = await request.body()
    base = f"{x_webhook_timestamp}.{body_bytes.decode('utf-8')}".encode('utf-8')
    expected = 'sha256=' + hmac.new(WEBHOOK_SECRET.encode('utf-8'), base, sha256).hexdigest()

    if not hmac.compare_digest(expected, x_webhook_signature):
        raise HTTPException(status_code=401, detail='invalid signature')

    payload = json.loads(body_bytes.decode('utf-8'))
    print('Received event:', payload.get('type'), 'sequence=', payload.get('sequence'))
    return {'ok': True}


if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8090)
