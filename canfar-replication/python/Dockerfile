FROM python:3.15.2-alpine3.24
WORKDIR /app

COPY ../requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY config.py .

CMD ["python3", "main.py"]