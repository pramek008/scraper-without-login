# Gunakan Python image versi 3
FROM python:3.9-slim

# Set work directory
WORKDIR /app

# Salin file requirements.txt ke dalam container
COPY requirements.txt .

# Install dependencies
# RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install -r requirements.txt && \
    playwright install --with-deps chromium

# Salin seluruh isi direktori saat ini ke dalam container
COPY . .
COPY .env .

RUN mkdir -p /app/token_storage && \
    touch /app/token_storage/tokens.json && \
    chmod 666 /app/token_storage/tokens.json

# Expose port 4000 untuk Flask
EXPOSE 4000

# Define environment variable
ENV PYTHONUNBUFFERED=1

# Jalankan aplikasi
# CMD ["flask", "run", "--host=0.0.0.0", "--port=4000"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "4000", "--timeout-keep-alive", "150","--reload"]
