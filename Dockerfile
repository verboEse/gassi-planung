FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN mkdir /data && chown 10001:10001 /data

USER 10001:10001
EXPOSE 8585
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8585"]
