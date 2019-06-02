FROM python:3.7

VOLUME /app
WORKDIR /app
COPY csbot ./csbot
COPY csbot.*.cfg requirements.txt run_csbot.py docker-entrypoint.sh ./
RUN find . -name '*.pyc' -delete

RUN pip install -r requirements.txt

ARG SOURCE_COMMIT
ENV SOURCE_COMMIT $SOURCE_COMMIT

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["./csbot.cfg"]
