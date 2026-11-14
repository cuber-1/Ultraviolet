FROM python:3.12-slim AS trainer

WORKDIR /app
COPY machine-learning/requirements.txt machine-learning/requirements.txt
RUN pip install --no-cache-dir -r machine-learning/requirements.txt
COPY machine-learning/cropfit machine-learning/cropfit
COPY machine-learning/download_ecocrop.py machine-learning/download_ecocrop.py
ENV PYTHONPATH=/app/machine-learning
ENV CROPFIT_TRAIN_DEVICE=cpu
RUN python machine-learning/download_ecocrop.py && python -m cropfit.training

FROM python:3.12-slim AS runtime

WORKDIR /app
COPY machine-learning/requirements-runtime.txt machine-learning/requirements-runtime.txt
RUN pip install --no-cache-dir -r machine-learning/requirements-runtime.txt
COPY machine-learning/cropfit machine-learning/cropfit
COPY --from=trainer /app/machine-learning/data/raw/ecocrop.csv machine-learning/data/raw/ecocrop.csv
COPY --from=trainer /app/machine-learning/artifacts/cropfit.joblib machine-learning/artifacts/cropfit.joblib
COPY --from=trainer /app/machine-learning/artifacts/cropfit.metadata.json machine-learning/artifacts/cropfit.metadata.json
ENV PYTHONPATH=/app/machine-learning
EXPOSE 8100
CMD ["uvicorn", "cropfit.api:app", "--host", "0.0.0.0", "--port", "8100"]
