# Forest smoke warning web app. Railway builds this automatically when it finds a Dockerfile.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    YOLO_CONFIG_DIR=/tmp/Ultralytics

WORKDIR /app

# CPU-only PyTorch first. The default Linux wheels bundle CUDA (several GB), which is slow to build
# and goes over Railway's 4 GB image limit on the Trial and Free plans. The server has no GPU anyway.
RUN pip install torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Railway tells the app which port to listen on through $PORT.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]
