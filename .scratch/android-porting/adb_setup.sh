#!/usr/bin/env bash
export PATH=/usr/bin:$PATH
echo "step0 start"
adb start-server > /tmp/adb_srv.log 2>&1
echo "server rc=$?"
cat /tmp/adb_srv.log 2>&1
echo "trying connect"
timeout 20 adb connect 192.168.1.11:39839 > /tmp/adb_conn.log 2>&1
echo "connect rc=$?"
cat /tmp/adb_conn.log 2>&1
echo "devices"
timeout 15 adb devices > /tmp/adb_dev.log 2>&1
echo "devices rc=$?"
cat /tmp/adb_dev.log 2>&1
echo "step done"
