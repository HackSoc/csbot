#!/bin/bash

if [[ ! -z "$ROLLBAR_ACCESS_TOKEN" ]] ; then
    curl https://api.rollbar.com/api/1/deploy/ \
        -F access_token=$ROLLBAR_ACCESS_TOKEN \
        -F environment=${ROLLBAR_ENV:-development} \
        -F revision=$SOURCE_COMMIT \
        -F local_username=`whoami`
fi

env
exec ./run_csbot.py $@
