FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY db/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY db/ .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
