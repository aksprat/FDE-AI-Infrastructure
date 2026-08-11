FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Overridden per-component (service/worker/migration job) by run_command in
# the App Platform spec — see infra/terraform/app.tf.
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"]
