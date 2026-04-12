FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

ARG APT_MIRROR_HOST=mirrors.aliyun.com
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
ARG PYTORCH_CPU_WHEEL_URL=https://mirrors.aliyun.com/pytorch-wheels/cpu/

RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i "s|http://deb.debian.org|https://${APT_MIRROR_HOST}|g; s|http://security.debian.org|https://${APT_MIRROR_HOST}|g" /etc/apt/sources.list.d/debian.sources; \
    fi \
    && if [ -f /etc/apt/sources.list ]; then \
        sed -i "s|http://deb.debian.org|https://${APT_MIRROR_HOST}|g; s|http://security.debian.org|https://${APT_MIRROR_HOST}|g" /etc/apt/sources.list; \
    fi \
    && apt-get -o Acquire::Retries=3 -o Acquire::ForceIPv4=true update \
    && apt-get -o Acquire::Retries=3 -o Acquire::ForceIPv4=true install -y --no-install-recommends ffmpeg libglib2.0-0 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
COPY requirements-torch.txt ./
RUN pip install --upgrade pip \
    && pip install --index-url ${PIP_INDEX_URL} --find-links ${PYTORCH_CPU_WHEEL_URL} --retries 5 --timeout 60 -r requirements-torch.txt \
    && pip install --index-url ${PIP_INDEX_URL} --retries 5 --timeout 60 -r requirements.txt

COPY requirements-extra.txt ./
RUN pip install --index-url ${PIP_INDEX_URL} --retries 5 --timeout 60 -r requirements-extra.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
