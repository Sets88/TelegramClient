#! /bin/bash
export TG_API_ID=INSERT_ID_HERE
export TG_API_HASH="INSERT_HASH_HERE"
export TG_PHONE="INSERT_PHONE_NUMBER"
export TG_USERNAME="INSERT_USERNAME"
export TG_ACCESS_HASH=INSERT_ACCESS_HASH
killall python3
screen -d -RR -S telega python3 client1.py
