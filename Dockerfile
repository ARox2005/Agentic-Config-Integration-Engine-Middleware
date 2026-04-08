FROM python:3.13-slim

WORKDIR /app

COPY middleware/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir uvicorn python-dotenv

# Ensure configs directory exists for tenant JSON storage
RUN mkdir -p configs

COPY middleware/ /app/

EXPOSE 7860

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "7860"]
