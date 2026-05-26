#!/bin/bash

# # Install required packages
# sudo apt-get update
# # Install the Paho MQTT C++ library and its dependencies.
# sudo apt-get install -y libpaho-mqtt-dev
# sudo apt-get install -y libpaho-mqttpp-dev

# # Install the Boost C++ Libraries and their development headers.
# # sudo apt-get install -y libboost-all-dev
# sudo apt-get install -y nlohmann-json3-dev

# Create and activate the virtual environment
uv sync
source ./venv/bin/activate
