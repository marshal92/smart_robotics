#!/bin/bash
echo "Building the Digital Twin Web UI..."

# Ensure nvm is loaded so we can use npm
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

npm run build

echo "Build complete! The 'dist' folder is ready for the ROS 2 web_server node."
