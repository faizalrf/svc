#!/bin/bash
# Script to open up the monitoring URL. The URL is populated here once the infrasetup is ready and ssh scripts are being generated. Faisal, 2024-08-25
url="http://52.90.146.22:3000"

# Detect if running under WSL
if grep -qEi "(Microsoft|WSL)" /proc/version &> /dev/null ; then
    # Running inside WSL
    # Use Python to open the URL using explorer.exe
    python3 -c "import webbrowser; webbrowser.register('explorer', None, webbrowser.BackgroundBrowser('explorer.exe')); webbrowser.get('explorer').open('$url')"
    exit 0
fi

# For other environments, use Python's webbrowser module
if command -v python3 &>/dev/null; then
    python3 -m webbrowser "$url"
elif command -v python &>/dev/null; then
    python -m webbrowser "$url"
else
    echo "Python is not available to open the URL."
    echo "Please open the following URL manually: $url"
fi