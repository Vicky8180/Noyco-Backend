# Use an official Python runtime as a parent image
FROM python:3.13.7-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
# This step is cached by Docker to speed up subsequent builds
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Command to run the agent when the container starts
# The -u flag ensures that logs are sent straight to Cloud Logging
CMD ["python", "-u", "main.py", "start"]