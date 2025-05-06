#!/bin/bash
# update_websocket_ip_simple.sh - Script to update WebSocket IP address in DeepBI
# This script updates both the .env file and the compiled frontend files
# using the same approach as the Install_CN.sh script

set -e  # Exit on error

# Display help message
show_help() {
    echo "Usage: $0 [options] <new_ip_address>"
    echo ""
    echo "This script updates the WebSocket IP address in both the .env file and the compiled frontend files."
    echo ""
    echo "Options:"
    echo "  -h, --help       Show this help message"
    echo "  -r, --restart    Restart DeepBI services after updating"
    echo ""
    echo "Example:"
    echo "  $0 192.168.1.100       # Update IP to 192.168.1.100"
    echo "  $0 -r 192.168.1.100    # Update IP and restart services"
    echo ""
}

# Parse command line arguments
RESTART_SERVICES=false
NEW_IP=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            show_help
            exit 0
            ;;
        -r|--restart)
            RESTART_SERVICES=true
            shift
            ;;
        *)
            if [[ -z "$NEW_IP" ]]; then
                NEW_IP="$1"
            else
                echo "Error: Unexpected argument: $1"
                show_help
                exit 1
            fi
            shift
            ;;
    esac
done

# Check if IP address is provided
if [[ -z "$NEW_IP" ]]; then
    echo "Error: No IP address provided"
    show_help
    exit 1
fi

# Validate IP address format
if ! [[ $NEW_IP =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Error: Invalid IP address format. Please use format: xxx.xxx.xxx.xxx"
    exit 1
fi

echo "=== DeepBI WebSocket IP Update Tool ==="
echo "This script will update the WebSocket IP address in both the .env file and the compiled frontend files."
echo ""

# Check if .env file exists
if [[ ! -f .env ]]; then
    echo "Error: .env file not found. Please run this script from the DeepBI root directory."
    exit 1
fi

# Check if frontend files exist
if [[ ! -f ./client/dist/vendors~app.js ]] || [[ ! -f ./client/dist/app.js ]]; then
    echo "Error: Frontend files not found. Please make sure DeepBI is properly installed."
    exit 1
fi

# Get current IP address and ports from .env file
CURRENT_IP=$(grep 'REACT_APP_SOCKET_URL=' .env | cut -d'=' -f2 | cut -d':' -f1)
SOCKET_PORT=$(grep 'REACT_APP_SOCKET_URL=' .env | cut -d'=' -f2 | cut -d':' -f2 | cut -d'/' -f1)
WEB_PORT=$(grep 'WEB_SERVER=' .env | cut -d'=' -f2 | cut -d':' -f2)
AI_WEB_PORT=$(grep 'AI_WEB_SERVER=' .env | cut -d'=' -f2 | cut -d':' -f2)

# Print the extracted values for debugging
echo "DEBUG: Extracted values from .env file:"
echo "  CURRENT_IP=$CURRENT_IP"
echo "  SOCKET_PORT=$SOCKET_PORT"
echo "  WEB_PORT=$WEB_PORT"
echo "  AI_WEB_PORT=$AI_WEB_PORT"

if [[ -z "$CURRENT_IP" ]]; then
    echo "Error: Could not determine current IP address from .env file."
    exit 1
fi

if [[ -z "$SOCKET_PORT" ]]; then
    SOCKET_PORT="8339"  # Default socket port
fi

if [[ -z "$WEB_PORT" ]]; then
    WEB_PORT="8338"  # Default web port
fi

if [[ -z "$AI_WEB_PORT" ]]; then
    AI_WEB_PORT="8340"  # Default AI web port
fi

echo "Current IP address: $CURRENT_IP"
echo "New IP address: $NEW_IP"
echo "Socket port: $SOCKET_PORT"
echo "Web port: $WEB_PORT"
echo "AI web port: $AI_WEB_PORT"
echo ""

# Confirm with user
read -p "Do you want to proceed with the update? (y/n): " CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
    echo "Operation cancelled."
    exit 0
fi

echo ""
echo "Updating IP address in .env file..."

# Update .env file using the same approach as Install_CN.sh
# Read the current .env file
env_content=$(cat .env)

# Print the current content for debugging
echo "Current .env content (relevant lines):"
grep -E "REACT_APP_SOCKET_URL|WEB_SERVER|AI_WEB_SERVER" .env

# Replace IP addresses in the content using a different approach
# Use | as delimiter to avoid issues with / in the URL
env_content=$(echo "$env_content" | sed "s|WEB_SERVER=$CURRENT_IP|WEB_SERVER=$NEW_IP|g")
env_content=$(echo "$env_content" | sed "s|REACT_APP_SOCKET_URL=$CURRENT_IP|REACT_APP_SOCKET_URL=$NEW_IP|g")
env_content=$(echo "$env_content" | sed "s|AI_WEB_SERVER=$CURRENT_IP|AI_WEB_SERVER=$NEW_IP|g")

# Save the updated content back to .env
echo "$env_content" > .env

echo "Updating IP address in compiled frontend files..."

# Update frontend files using the same approach as Install_CN.sh
os_name=$(uname)
if [[ "$os_name" == "Darwin" ]]; then
    # macOS version
    sed -i '' "s|$CURRENT_IP:$SOCKET_PORT|$NEW_IP:$SOCKET_PORT|g" ./client/dist/vendors~app.js
    sed -i '' "s|$CURRENT_IP:$SOCKET_PORT|$NEW_IP:$SOCKET_PORT|g" ./client/dist/app.js
else
    # Linux version
    sed -i "s|$CURRENT_IP:$SOCKET_PORT|$NEW_IP:$SOCKET_PORT|g" ./client/dist/vendors~app.js
    sed -i "s|$CURRENT_IP:$SOCKET_PORT|$NEW_IP:$SOCKET_PORT|g" ./client/dist/app.js
fi

# Verify that the frontend files were updated
echo "Verifying frontend files update..."
if grep -q "$NEW_IP:$SOCKET_PORT" ./client/dist/app.js; then
    echo "Frontend files updated successfully!"
else
    echo "Warning: Could not verify frontend files update. This might be normal if the files are binary."
    echo "The update should still work as long as there were no errors above."
fi

echo "IP address updated successfully!"
echo ""

# Restart services if requested
if [[ "$RESTART_SERVICES" == true ]]; then
    echo "Restarting DeepBI services..."

    # Check if running in Docker
    if command -v docker-compose &> /dev/null && [[ -f docker-compose.yml ]]; then
        docker-compose restart
    else
        echo "Docker Compose not found or not running in Docker environment."
        echo "Please restart DeepBI services manually."
    fi
else
    echo "Note: DeepBI services need to be restarted for changes to take effect."
    echo "You can restart services with: docker-compose restart"
fi

echo ""
echo "Done!"
