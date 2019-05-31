FROM ubuntu:18.04

# From python:3.5 docker image, set locale
ENV LANG C.UTF-8

VOLUME /app
WORKDIR /app

# Update base OS
RUN apt-get -y update && apt-get -y upgrade
# Install useful tools
RUN apt-get -y install git curl
# Install Python 3(.4)
RUN apt-get -y install python3 python3-dev python-virtualenv
# Install dependencies for Python libs
RUN apt-get -y install libxml2-dev libxslt1-dev zlib1g-dev

# Copy needed files to build docker image
ADD requirements.txt docker-entrypoint.sh ./

# Create virtualenv
RUN virtualenv -p python3 /venv
# Populate virtualenv
RUN ./docker-entrypoint.sh pip install --upgrade pip
RUN ./docker-entrypoint.sh pip install -r requirements.txt

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["./run_csbot.py", "csbot.cfg"]
