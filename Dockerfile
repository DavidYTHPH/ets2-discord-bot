# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install ffmpeg directly into the operating system
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean

# Copy requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your bot's code
COPY . .

# Run the bot
CMD ["python", "main.py"]
