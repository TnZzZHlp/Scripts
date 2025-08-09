#!/bin/bash

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    apt update -y
    apt install -y jq
fi

# Check if unzip is installed
if ! command -v unzip &> /dev/null; then
    apt update -y
    apt install -y unzip
fi

echo "Retrieving latest Xray version..."

download_url=$(curl -s https://api.github.com/repos/XTLS/Xray-core/releases/latest | jq -r '.assets[] | select(.name | test("Xray-linux-64")) | .browser_download_url')

if [ -z "$download_url" ]; then
    echo "Failed to retrieve the download URL for the latest version of Xray."
    exit 1
fi

echo "Latest Xray download URL: $download_url"

# Download the latest Xray release
curl -L -o /tmp/xray.zip "$download_url"

if [ $? -ne 0 ]; then
    echo "Failed to download the latest Xray release."
    exit 1
fi

# Unzip the downloaded file
unzip /tmp/xray.zip -d /tmp/xray

if [ $? -ne 0 ]; then
    echo "Failed to unzip the latest Xray release."
    exit 1
fi

# Move the Xray binary to the appropriate location
mv /tmp/xray/xray /usr/local/bin/

if [ $? -ne 0 ]; then
    echo "Failed to move the Xray binary to /usr/local/bin/"
    # Remove the downloaded files
    rm -rf /tmp/xray.zip /tmp/xray
    exit 1
fi

echo "Xray has been successfully upgraded to the latest version."
systemctl restart xray