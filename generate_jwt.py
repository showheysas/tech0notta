import jwt
import time
import os
from dotenv import load_dotenv

load_dotenv()

SDK_KEY = os.getenv("ZOOM_SDK_KEY")
SDK_SECRET = os.getenv("ZOOM_SDK_SECRET")

if not SDK_KEY or not SDK_SECRET:
    print("Error: ZOOM_SDK_KEY or ZOOM_SDK_SECRET not found in .env")
    exit(1)

def generate_jwt(key, secret):
    now = int(time.time())
    payload = {
        "appKey": key,
        "iat": now,
        "exp": now + 86400, # 24 hours
        "tokenExp": now + 86400
    }
    
    token = jwt.encode(payload, secret, algorithm="HS256")
    return token

if __name__ == "__main__":
    token = generate_jwt(SDK_KEY, SDK_SECRET)
    print(f"JWT_TOKEN=\"{token}\"")
