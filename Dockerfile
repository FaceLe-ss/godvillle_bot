FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY webapp ./webapp
COPY pyproject.toml README.md ./

RUN mkdir -p /app/data

EXPOSE 8080

CMD ["python", "-m", "godville_bot.main"]
