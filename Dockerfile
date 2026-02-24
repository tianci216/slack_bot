FROM python:3.11-slim

WORKDIR /app

# Make core/ importable from anywhere inside the container
ENV PYTHONPATH=/app

# Install core dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy core framework only
# functions/ and data/ are mounted as volumes at runtime
COPY core/ core/
COPY main.py .

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
