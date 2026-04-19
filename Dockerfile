FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DB_TYPE=sqlite
ENV DB_FILE=/app/data/a_daily_quant.db
ENV APP_HOST=0.0.0.0
ENV APP_PORT=8100
ENV APP_RELOAD=false

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN mkdir -p /app/data

EXPOSE 8100

CMD ["python", "start.py"]
