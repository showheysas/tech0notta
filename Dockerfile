FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libpq-dev \
    xvfb \
    pulseaudio \
    pulseaudio-utils \
    libasound2-plugins \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Python package + Chromium browser binary + system dependencies
RUN pip install --no-cache-dir playwright==1.44.0 && \
    playwright install chromium && \
    playwright install-deps chromium

COPY app ./app

# Bot scripts at absolute paths expected by entrypoint.py
COPY app/bot_runner/setup-pulseaudio.sh /app/setup-pulseaudio.sh
COPY app/bot_runner/audio_capture.sh    /app/audio_capture.sh
COPY app/bot_runner/realtime_transcriber.py /app/realtime_transcriber.py
COPY app/bot_runner/upload_workflow.py  /app/upload_workflow.py
RUN chmod +x /app/setup-pulseaudio.sh /app/audio_capture.sh && \
    sed -i 's/\r//' /app/setup-pulseaudio.sh /app/audio_capture.sh

# Fake media files for Chrome's fake device mode
RUN python3 -c 'w,h=640,360; uv=(w//2)*(h//2); f=open("/app/black.y4m","wb"); f.write(("YUV4MPEG2 W"+str(w)+" H"+str(h)+" F30:1 Ip A0:0 C420\n").encode()); f.write(b"FRAME\n"); f.write(bytes(w*h)); f.write(bytes([128]*uv)); f.write(bytes([128]*uv)); f.close()'
RUN python3 -c 'import wave; f=wave.open("/app/silent.wav","wb"); f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000); f.writeframes(bytes(16000*2)); f.close()'

RUN mkdir -p /app/recordings

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
