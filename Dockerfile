FROM python:3.5

RUN pip install asyncio-redis==0.14.3

COPY ./asyncio_redis_ha /code/asyncio_redis_ha
COPY ./tests /code/tests