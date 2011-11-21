#!/bin/bash

instances=4
start_port=9921

mustash()
{
  cmd=$1
  for port in `jot $instances $start_port`
  do
    export PORT=$port
    /opt/mustash/scripts/debian-init.sh $cmd
  done
}

case "$1" in
  start)
    mustash start
    ;;
  stop)
    mustash stop
    ;;
  restart|reload)
    mustash restart
    ;;
  status)
    mustash status
    ;;
esac
