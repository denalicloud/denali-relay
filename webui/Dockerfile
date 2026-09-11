FROM python:3.12-slim

RUN pip install flask==3.1.0

WORKDIR /app
COPY app.py .
COPY templates/ templates/

EXPOSE 8080

CMD ["python3", "app.py"]
