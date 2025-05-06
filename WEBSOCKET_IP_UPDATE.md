# DeepBI WebSocket IP Update Guide

## The Problem

In DeepBI, when you modify the IP address in the `.env` file after installation, the WebSocket connections may still fail. This is because the WebSocket addresses are hardcoded in the frontend JavaScript files during the build process.

The issue occurs because:

1. During installation, the `Install_CN.sh` script sets the IP address in two places:
   - In the `.env` file through the `REACT_APP_SOCKET_URL` variable
   - Directly in the compiled frontend JavaScript files (`client/dist/vendors~app.js` and `client/dist/app.js`)

2. When you later change the IP address in the `.env` file, the frontend code still uses the old hardcoded IP address for WebSocket connections.

## The Solution

To properly update the WebSocket IP address, you need to:

1. Update the IP address in the `.env` file
2. Update the hardcoded IP address in the compiled frontend JavaScript files
3. Restart the DeepBI services

We've created scripts to automate this process for you.

## Using the Update Scripts

We've provided two scripts:

- `update_websocket_ip.sh` - For Linux systems
- `update_websocket_ip_mac.sh` - For macOS systems (uses a different `sed` syntax)

### Basic Usage

1. Make the script executable (if not already):
   ```bash
   chmod +x update_websocket_ip.sh  # For Linux
   # OR
   chmod +x update_websocket_ip_mac.sh  # For macOS
   ```

2. Run the script with your new IP address:
   ```bash
   ./update_websocket_ip.sh 192.168.1.100  # For Linux
   # OR
   ./update_websocket_ip_mac.sh 192.168.1.100  # For macOS
   ```

3. The script will:
   - Show you the current and new IP addresses
   - Ask for confirmation before making changes
   - Update the IP address in both the `.env` file and the frontend files
   - Remind you to restart the DeepBI services

### Restarting Services Automatically

You can add the `-r` or `--restart` flag to automatically restart the DeepBI services after updating the IP:

```bash
./update_websocket_ip.sh -r 192.168.1.100  # For Linux
# OR
./update_websocket_ip_mac.sh -r 192.168.1.100  # For macOS
```

### Getting Help

To see all available options:

```bash
./update_websocket_ip.sh --help  # For Linux
# OR
./update_websocket_ip_mac.sh --help  # For macOS
```

## Manual Update Process

If you prefer to update the IP address manually, follow these steps:

1. Update the IP address in the `.env` file:
   ```
   REACT_APP_SOCKET_URL=new_ip:8339/chat/
   WEB_SERVER=new_ip:8338
   AI_WEB_SERVER=new_ip:8340
   ```

2. Update the hardcoded IP address in the frontend files:
   ```bash
   # For Linux:
   sed -i "s|old_ip:8339|new_ip:8339|g" ./client/dist/vendors~app.js
   sed -i "s|old_ip:8339|new_ip:8339|g" ./client/dist/app.js
   
   # For macOS:
   sed -i '' "s|old_ip:8339|new_ip:8339|g" ./client/dist/vendors~app.js
   sed -i '' "s|old_ip:8339|new_ip:8339|g" ./client/dist/app.js
   ```

3. Restart the DeepBI services:
   ```bash
   docker-compose restart
   ```

## Troubleshooting

If you encounter issues:

1. Make sure you're running the script from the DeepBI root directory
2. Verify that the `.env` file and frontend files exist
3. Check that you have write permissions for these files
4. If using Docker, ensure that Docker Compose is installed and running

For further assistance, please open an issue on the DeepBI GitHub repository.
