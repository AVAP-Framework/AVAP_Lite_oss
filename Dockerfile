FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/src/

COPY app/ /app/app/
COPY avap.proto /app/

EXPOSE 8888
ENV PYTHONPATH="/app"
CMD ["python", "-u", "src/main.py"]
