#!/usr/bin/env bash

# Weather for Sheffield, UK
LOCATION="Sheffield"

# Fetch and display weather (simple format)
curl -s "https://wttr.in/${LOCATION}?format=3"
echo

# Optional: full detailed forecast (uncomment if you want more info)
#curl -s "https://wttr.in/${LOCATION}"
