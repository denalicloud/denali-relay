FROM python:3.12-slim

RUN pip install redis

WORKDIR /app
COPY policy.py .

EXPOSE 10031

CMD ["python3", "policy.py"]
