FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY app.py ./
COPY sourcing ./sourcing
COPY taste ./taste
COPY checkout ./checkout
COPY finance ./finance
COPY voice ./voice
# niche-indie's seed list, sent along with a shopper's own shops (sourcing/sources.py)
COPY actors/niche_actors ./actors/niche_actors
RUN pip install --no-cache-dir .
CMD ["python", "-m", "sourcing.actor"]
