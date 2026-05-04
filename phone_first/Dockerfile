FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml README.md uv.lock ./
COPY backend ./backend
COPY assistant_service ./assistant_service

RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev

CMD ["uv", "run", "phone-first-assistant-stable"]
