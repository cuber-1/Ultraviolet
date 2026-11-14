FROM python:3.12-slim AS trainer

WORKDIR /app
COPY ml/requirements.txt ml/requirements.txt
RUN pip install --no-cache-dir -r ml/requirements.txt
COPY ml/cropfit ml/cropfit
COPY ml/download_ecocrop.py ml/download_ecocrop.py
ENV PYTHONPATH=/app/ml
ENV CROPFIT_TRAIN_DEVICE=cpu
RUN python ml/download_ecocrop.py && python -m cropfit.training

FROM python:3.12-slim AS runtime

WORKDIR /app
COPY ml/requirements-runtime.txt ml/requirements-runtime.txt
RUN pip install --no-cache-dir -r ml/requirements-runtime.txt
COPY ml/cropfit ml/cropfit
COPY --from=trainer /app/ml/data/raw/ecocrop.csv ml/data/raw/ecocrop.csv
COPY --from=trainer /app/ml/artifacts/cropfit.joblib ml/artifacts/cropfit.joblib
COPY --from=trainer /app/ml/artifacts/cropfit.metadata.json ml/artifacts/cropfit.metadata.json
ENV PYTHONPATH=/app/ml
EXPOSE 8100
CMD ["uvicorn", "cropfit.api:app", "--host", "0.0.0.0", "--port", "8100"]
