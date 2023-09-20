# Use the slim Python 3.11 image as the base image
# We use 'slim' instead of 'alpine' because 'slim' includes C dependencies
# that are needed for the cryptography package, while still being small in size.
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the contents of the current directory into the container at /app
COPY . .

# Install project dependencies from the requirements file
RUN pip install --no-cache-dir -r requirements-production.txt

# Set environment variable for PORT
ENV PORT=5000

# Run the Quart app when the container starts
# Adapt the workers and keep-alive parameters to the deployment requirements
ENTRYPOINT hypercorn --bind :$PORT --workers 1 --keep-alive 15 app:app
