#!/bin/bash

if [[ ! -d "venv" ]]; then
    ./init.sh
fi

source venv/bin/activate
python3 ./임시.py
