FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY app.py ./
COPY sourcing ./sourcing
COPY taste ./taste
COPY checkout ./checkout
RUN pip install --no-cache-dir .
CMD ["python", "-m", "sourcing.actor"]
