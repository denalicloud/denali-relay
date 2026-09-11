FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    gcc \
    libmilter-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install pymilter dkimpy

WORKDIR /app
COPY dkim_milter.py .

EXPOSE 8891

CMD ["python3", "dkim_milter.py"]
