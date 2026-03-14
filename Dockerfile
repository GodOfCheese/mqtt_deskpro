FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY cisco_deskpro_mqtt.py .
COPY deskpro.py .

# Run the bridge
CMD ["python", "cisco_deskpro_mqtt.py"]
