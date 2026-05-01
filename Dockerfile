FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Создаём папку для ассетов если нет generate_images
RUN mkdir -p /app/assets && \
    if [ -f generate_images.py ]; then python3 generate_images.py; fi

CMD ["python", "bot.py"]
