// import notification from "@/services/notification";
import { currentUser } from "@/services/auth";
import { EventEmitter } from 'events';
import { getWebSocketUrl } from "@/services/websocketConfig";

let websocket,
  lockReconnect = false,
  wsType = 0,
  stopGeneration = true;
const lockReconnectEvent = new EventEmitter();

let createWebSocket = async () => {
  if (websocket && websocket.readyState === 1) return;

  try {
    // Get WebSocket URL from the config service
    const url = await getWebSocketUrl(currentUser);

    websocket = new WebSocket(url);
    websocket.onopen = function () {
      heartCheck.reset().start();
      // notification.success(window.W_L.connection_success_tip)
      lockReconnect = true;
      stopGeneration = false;
      wsType = 1;
      lockReconnectEvent.emit('change', wsType);
    };
    websocket.onerror = function (e) {
      reconnect(url);
    };
    websocket.onclose = function (e) {
      lockReconnect = false;
      wsType = 0;
      lockReconnectEvent.emit('change', wsType);
    };
    websocket.onmessage = function (event) {
      lockReconnect = true;
      wsType = 1;
      lockReconnectEvent.emit('change', wsType);
    };
  } catch (error) {
    console.error('Failed to create WebSocket connection:', error);
    lockReconnect = false;
    wsType = 0;
    lockReconnectEvent.emit('change', wsType);
  }
};
let reconnect = (url) => {
  if (lockReconnect) return;
  setTimeout(async function () {
    await createWebSocket();
    lockReconnect = false;
    wsType = 2;
    lockReconnectEvent.emit('change', wsType);
  }, 4000);
};
let heartCheck = {
  timeout: 60000,
  timeoutObj: null,
  reset: function () {
    clearInterval(this.timeoutObj);
    return this;
  },
  start: function () {
    this.timeoutObj = setInterval(function () {
      const messgaeInfo = {
        state:200,
        sender:"heartCheck",
        data: {
          content:"HeartBeat",
        },
      }
      sendMessage(messgaeInfo)
    }, this.timeout);
  },
};
let sendMessage = (message) => {
  if (websocket && websocket.readyState === 1) {
    websocket.send(JSON.stringify(message));
  }
};
let closeWebSocket = () => {
  websocket && websocket.close();
};
let setLockReconnect = (flag) => {
  lockReconnect = flag;
};
let setStopGeneration = (flag) => {
  stopGeneration = flag;
};
export { websocket, createWebSocket, closeWebSocket,lockReconnect,setLockReconnect,stopGeneration,setStopGeneration,lockReconnectEvent };
