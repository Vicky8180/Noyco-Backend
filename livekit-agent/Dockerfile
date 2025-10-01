# Use an official Python runtime as a parent image
FROM python:3.13.7-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
# This is cached to speed up builds if requirements don't change
COPY livekit-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the agent's application code into the container
COPY livekit-agent/ .

# Make startup script executable
RUN chmod +x startup.sh

# Expose the port that Cloud Run expects
EXPOSE 8080

# Set environment variable for PORT (Cloud Run will override this)
ENV PORT=8080

# Command to run the agent server with health check endpoint
CMD ["python", "-u", "server.py"]