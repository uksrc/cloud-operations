#!/bin/bash
cp /etc/letsencrypt/live/xrootd01.cam.uksrc.org/fullchain.pem /etc/grid-security/xrootd/hostcert.pem
cp /etc/letsencrypt/live/xrootd01.cam.uksrc.org/privkey.pem /etc/grid-security/xrootd/hostkey.pem
systemctl restart xrootd@config
