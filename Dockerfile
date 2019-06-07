FROM python:3.7

VOLUME /app
WORKDIR /app
COPY src ./src
COPY tests ./tests
COPY setup.py requirements.txt pytest.ini docker-entrypoint.sh csbot.*.cfg ./

RUN pip install -r requirements.txt

ARG SOURCE_COMMIT
ENV SOURCE_COMMIT $SOURCE_COMMIT

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["./csbot.cfg"]
