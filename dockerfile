FROM python:3.11.4-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt
RUN playwright install --with-deps

COPY . .

VOLUME ["/app/db"]
VOLUME ["/app/logs"]

CMD ["python", "main.py"]