FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
# app/ must be present before the editable install, since pyproject pins
# packages=["app"] and setuptools verifies the package dir exists.
COPY app/ app/
RUN pip install --no-cache-dir -e .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
