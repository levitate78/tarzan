FROM python:3.12-slim AS builder

WORKDIR /app

# Security: run as non-root
RUN groupadd -r tarzan && useradd -r -g tarzan tarzan

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim AS runtime

WORKDIR /app

RUN groupadd -r tarzan && useradd -r -g tarzan tarzan

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin /usr/local/bin

COPY --chown=tarzan:tarzan . .

USER tarzan

CMD ["python", "-u", "app/main.py"]
