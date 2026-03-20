# 1. Use an official, lightweight Python base image
FROM python:3.13-slim

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Install 'uv' for lightning-fast dependency resolution
RUN pip install uv

# 4. Copy ONLY the requirements first. 
# We do this before copying the code so Docker can cache the installed packages!
COPY src/requirements.txt .

# 5. Use uv to install dependencies directly into the system Python
RUN uv pip install --system --no-cache -r requirements.txt

# 6. Copy your application source code into the container
COPY src/ .

# 7. Set the Python Path so it knows where your modules are
ENV PYTHONPATH=/app

# 8. Expose the port that Cloud Run expects
EXPOSE 8002

# 9. Start the FastAPI server using Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]

