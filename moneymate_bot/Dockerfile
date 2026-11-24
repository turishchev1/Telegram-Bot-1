FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The database lives in /app/data: mount a volume there so it survives restarts and updates.
VOLUME ["/app/data"]

CMD ["python", "bot.py"]
