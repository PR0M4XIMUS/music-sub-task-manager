# For many Raspberry Pi setups this works out-of-the-box.
# If your Pi Zero image needs armv6 specifically, you may switch to an armv6 base.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure data dir exists
RUN mkdir -p /app/data

CMD ["python", "bot.py"]
