FROM python:3.13-slim

WORKDIR /workspace

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY app ./app

CMD ["python", "-m", "flask", "--app", "app", "run", "--host", "0.0.0.0", "--port", "5000"]