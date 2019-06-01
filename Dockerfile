FROM python:3.7

VOLUME /app
WORKDIR /app
COPY csbot ./csbot
COPY csbot.*.cfg requirements.txt run_csbot.py docker-entrypoint.sh ./

RUN pip install -r requirements.txt

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["./csbot.cfg"]
