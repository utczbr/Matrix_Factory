const WebSocket = require('ws');
const fs = require('fs');

const ws = new WebSocket('ws://127.0.0.1:8080/telemetry?run_id=0&client=test');

ws.on('open', function open() {
  console.log('connected');
});

ws.on('message', function incoming(data) {
  console.log('received size:', data.length);
  fs.writeFileSync('frame.bin', data);
  ws.close();
});

ws.on('error', function(e) {
  console.error(e);
});
