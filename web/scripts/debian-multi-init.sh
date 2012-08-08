#!/bin/bash
### BEGIN INIT INFO
# Provides:          mustash
# Required-Start:    $local_fs $syslog
# Required-Stop:     $local_fs $syslog
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: musta.sh web server
# Description:       musta.sh web server
### END INIT INFO

instances=4
start_port=9921

mustash()
{
  cmd=$1
  cpu=0
  for port in `jot $instances $start_port`
  do
    export PORT=$port
    /opt/mustash/scripts/debian-init.sh $cmd
    pidfile=/var/run/musta.py.$PORT.pid
    [ -r $pidfile ] && taskset -pc $cpu `cat $pidfile`
    cpu=$[cpu+1]
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
