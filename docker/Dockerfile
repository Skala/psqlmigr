FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy core engine source code
COPY core_engine /app/core_engine

# Install psqlmigr-core package
RUN pip install --no-cache-dir /app/core_engine

ENTRYPOINT ["psqlmigr"]
CMD ["status"]
