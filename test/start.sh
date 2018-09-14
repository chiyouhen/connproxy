#! /bin/bash

testdir=$(cd $(dirname $0) && pwd)
basedir=$(dirname $testdir)
PYTHONPATH=$basedir:$PYTHONPATH
export PYTHONPATH
exec "$@"
