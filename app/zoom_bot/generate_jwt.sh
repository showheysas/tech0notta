#!/bin/bash
# .envからSDK Key/Secretを読み込み、Docker内のPythonを使ってJWTを生成するスクリプト

export $(grep -v '^#' ../../.env | xargs)

if [ -z "$ZOOM_SDK_KEY" ] || [ -z "$ZOOM_SDK_SECRET" ]; then
    echo "Error: ZOOM_SDK_KEY or ZOOM_SDK_SECRET not found in .env"
    exit 1
fi

# PyJWTがインストールされたDockerイメージを使ってJWT生成
docker run --rm --entrypoint python3 tech-notta-bot:latest -c "
import jwt
import time
import sys

key = '$ZOOM_SDK_KEY'
secret = '$ZOOM_SDK_SECRET'
iat = int(time.time())
exp = iat + 60 * 60 * 24 # 24 hours

payload = {
    'appKey': key, 
    'iat': iat, 
    'exp': exp, 
    'tokenExp': exp
}

token = jwt.encode(payload, secret, algorithm='HS256')
# バイト列ならデコード
if isinstance(token, bytes):
    token = token.decode('utf-8')
print(token)
"
