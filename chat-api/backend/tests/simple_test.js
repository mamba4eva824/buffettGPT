const WebSocket = require('ws');

const url = 'wss://52x14spfai.execute-api.us-east-1.amazonaws.com/dev?user_id=test-user-123';

console.log('🔌 Connecting to:', url);

const ws = new WebSocket(url);

ws.on('open', function open() {
    console.log('✅ Connected to WebSocket!');
    
    // Send a ping message
    const pingMessage = {
        action: 'ping',
        message_id: 'test-ping-' + Date.now()
    };
    
    console.log('📤 Sending ping:', JSON.stringify(pingMessage));
    ws.send(JSON.stringify(pingMessage));
    
    // Send a chat message after 2 seconds
    setTimeout(() => {
        const chatMessage = {
            action: 'message',
            message: 'Hello Warren! What is your investment philosophy?',
            message_id: 'test-msg-' + Date.now()
        };
        
        console.log('📤 Sending chat message:', JSON.stringify(chatMessage));
        ws.send(JSON.stringify(chatMessage));
    }, 2000);
    
    // Close connection after 10 seconds
    setTimeout(() => {
        console.log('🔌 Closing connection...');
        ws.close();
    }, 10000);
});

ws.on('message', function message(data) {
    console.log('📥 Received:', data.toString());
});

ws.on('close', function close() {
    console.log('🔌 Connection closed');
});

ws.on('error', function error(err) {
    console.error('❌ WebSocket error:', err);
});
