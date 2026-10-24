# Shared by all three actors; ACTOR_MODULE picks which one runs (set in each .actor/actor.json build env).
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "httpx>=0.27,<1"
COPY niche_actors ./niche_actors
ARG ACTOR_MODULE=mainstream
ENV ACTOR_MODULE=${ACTOR_MODULE}
CMD python -m niche_actors.${ACTOR_MODULE}
