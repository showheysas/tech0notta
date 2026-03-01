#!/bin/bash
set -e
Xvfb :99 -screen 0 1280x720x24 > /dev/null 2>&1 &
export DISPLAY=:99
sleep 1
exec python3 /app/entrypoint.py "$@"
