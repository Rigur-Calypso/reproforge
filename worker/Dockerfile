FROM python:3.13-slim

RUN pip install --no-cache-dir pytest==8.4.2 pytest-timeout==2.4.0 \
    && mkdir -p /opt/reproforge /candidate

WORKDIR /workspace
USER 65532:65532
