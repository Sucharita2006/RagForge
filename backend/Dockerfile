FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git \
    libgl1 libglib2.0-0 libxcb1 libxext6 libsm6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip
# CPU-only torch wheel (~200MB) instead of PyPI's default CUDA-bundled one
# (~530MB, and repeatedly stalled mid-download through Docker Desktop's
# network layer on this machine) — also just correct for our CPU-only
# profile (implementation-plan.md §3). docker-compose.gpu.yml overrides the
# index with a CUDA build for machines that have an NVIDIA GPU.
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir torch torchvision --index-url ${TORCH_INDEX}
RUN pip install --no-cache-dir -e ".[dev]"
# minicheck's sentence splitter needs this NLTK resource at call time, not
# import time - baked in at build time (a few MB, deterministic) rather
# than left as a first-query lazy download over the network like the much
# larger HF model checkpoints (implementation-plan.md §3).
RUN python -c "import nltk; nltk.download('punkt_tab')"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
