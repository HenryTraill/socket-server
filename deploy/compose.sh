#!/usr/bin/env bash
set -e
if [ "$MODE" != "PRODUCTION" ]; then
    echo "environment variable APP_MASTER_KEY not set or blank"
    exit 2
fi
export COMMIT=`git rev-parse HEAD`
export RELEASE_DATE=`date`
the_command="docker-compose -f docker-compose.yml -f docker-compose.prod.yml $@"
echo "Running '${the_command}'..."
eval ${the_command}
