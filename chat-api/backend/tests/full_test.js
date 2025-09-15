const WebSocket = require('ws');

const url = 'wss://52x14spfai.execute-api.us-east-1.amazonaws.com/dev?user_id=test-user-123';

console.log('🔌 Connecting to:', url);

const ws = new WebSocket(url);

ws.on('open', function open() {
    console.log('✅ Connected to WebSocket!');
    
    // Send a chat message
    const chatMessage = {
        action: 'message',
        message: 'Hello Warren! What are your top 3 investment principles?',
        message_id: 'test-msg-' + Date.now()
    };
    
    console.log('📤 Sending chat message:', JSON.stringify(chatMessage));
    ws.send(JSON.stringify(chatMessage));
});

ws.on('message', function message(data) {
    const response = JSON.parse(data.toString());
    console.log('📥 Received:', JSON.stringify(response, null, 2));
    
    // If we get the AI response, close the connection
    if (response.action === 'ai_response') {
        console.log('🎉 Got AI response! Closing connection...');
        setTimeout(() => {
            ws.close();
        }, 1000);
    }
});

ws.on('close', function close() {
    console.log('🔌 Connection closed');
});

ws.on('error', function error(err) {
    console.error('❌ WebSocket error:', err);
});

// Keep the connection open for 30 seconds to wait for AI response
setTimeout(() => {
    if (ws.readyState === WebSocket.OPEN) {
        console.log('⏰ Test timeout - closing connection');
        ws.close();
    }
}, 30000);
