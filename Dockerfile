# Use a lightweight official Python image as the base
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all the rest of the application files into the container
COPY . .

# Expose the port that the application will listen on
EXPOSE 5000

# Set the command to run the application using Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]