FROM python:3.12-slim

WORKDIR /app
COPY machine-learning/requirements-runtime.txt machine-learning/requirements-runtime.txt
RUN pip install --no-cache-dir -r machine-learning/requirements-runtime.txt
COPY machine-learning/cropfit machine-learning/cropfit
COPY machine-learning/demo_vectors.json machine-learning/demo_vectors.json
ENV PYTHONPATH=/app/machine-learning
EXPOSE 8100
CMD ["uvicorn", "cropfit.api:app", "--host", "0.0.0.0", "--port", "8100"]
