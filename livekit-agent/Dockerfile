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

# Command to run the agent when the container starts
CMD ["python", "-u", "main.py", "start"]