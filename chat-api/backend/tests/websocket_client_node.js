#!/usr/bin/env node
/**
 * WebSocket Client Test Script (Node.js)
 * Alternative WebSocket testing implementation in Node.js
 */

const WebSocket = require('ws');
const { v4: uuidv4 } = require('uuid');

class WebSocketChatTester {
    constructor(websocketUrl, userId, sessionId = null) {
        this.websocketUrl = websocketUrl;
        this.userId = userId;
        this.sessionId = sessionId || uuidv4();
        this.ws = null;
        this.connected = false;
        this.messageCount = 0;
        this.responsesReceived = 0;
    }

    async connect() {
        return new Promise((resolve, reject) => {
            try {
                const connectionUrl = `${this.websocketUrl}?user_id=${this.userId}&session_id=${this.sessionId}`;
                
                console.log(`🔌 Connecting to: ${connectionUrl}`);
                
                this.ws = new WebSocket(connectionUrl);
                
                this.ws.on('open', () => {
                    this.connected = true;
                    console.log('✅ Connected successfully!');
                    console.log(`   User ID: ${this.userId}`);
                    console.log(`   Session ID: ${this.sessionId}`);
                    resolve(true);
                });
                
                this.ws.on('error', (error) => {
                    console.error('❌ Connection error:', error.message);
                    reject(error);
                });
                
                this.ws.on('close', () => {
                    this.connected = false;
                    console.log('🔌 Connection closed');
                });
                
                this.ws.on('message', (data) => {
                    try {
                        const message = JSON.parse(data.toString());
                        const action = message.action || 'unknown';
                        console.log(`📥 Received: ${action} - ${data.toString().substring(0, 100)}...`);
                        
                        // Store last received message for tests
                        this.lastReceivedMessage = message;
                        this.responsesReceived++;
                    } catch (e) {
                        console.error('❌ Failed to parse received message:', e.message);
                    }
                });
                
                // Set connection timeout
                setTimeout(() => {
                    if (!this.connected) {
                        reject(new Error('Connection timeout'));
                    }
                }, 10000);
                
            } catch (error) {
                reject(error);
            }
        });
    }

    async disconnect() {
        if (this.ws && this.connected) {
            this.ws.close();
            this.connected = false;
            console.log('🔌 Disconnected');
        }
    }

    async sendMessage(message) {
        return new Promise((resolve, reject) => {
            try {
                if (!this.connected || !this.ws) {
                    console.error('❌ Not connected');
                    resolve(false);
                    return;
                }
                
                const messageJson = JSON.stringify(message);
                this.ws.send(messageJson);
                
                console.log(`📤 Sent: ${message.action || 'unknown'} - ${messageJson.substring(0, 100)}...`);
                resolve(true);
                
            } catch (error) {
                console.error('❌ Failed to send message:', error.message);
                resolve(false);
            }
        });
    }

    async waitForMessage(timeout = 30000) {
        return new Promise((resolve) => {
            const startResponses = this.responsesReceived;
            
            const checkForNewMessage = () => {
                if (this.responsesReceived > startResponses) {
                    resolve(this.lastReceivedMessage);
                } else if (timeout > 0) {
                    setTimeout(checkForNewMessage, 100);
                    timeout -= 100;
                } else {
                    console.log('⏰ Timeout waiting for message');
                    resolve(null);
                }
            };
            
            checkForNewMessage();
        });
    }

    async sendPing() {
        const pingMessage = {
            action: 'ping',
            message_id: `ping-${Date.now()}`
        };
        return await this.sendMessage(pingMessage);
    }

    async sendChatMessage(text) {
        this.messageCount++;
        const chatMessage = {
            action: 'message',
            message: text,
            message_id: `msg-${this.messageCount}-${Date.now()}`
        };
        return await this.sendMessage(chatMessage);
    }

    async runBasicTest() {
        console.log('🧪 Running Basic WebSocket Test');
        console.log('=' * 40);
        
        const results = {
            testName: 'Basic WebSocket Test',
            passed: false,
            details: {},
            errors: []
        };

        try {
            // Test 1: Connection
            console.log('🧪 Test 1: Connection');
            const connected = await this.connect();
            if (!connected) {
                results.errors.push('Failed to establish connection');
                return results;
            }
            results.details.connection = '✅ Success';

            // Wait a moment for connection to stabilize
            await new Promise(resolve => setTimeout(resolve, 1000));

            // Test 2: Ping/Pong
            console.log('🧪 Test 2: Ping/Pong');
            const pingSent = await this.sendPing();
            if (!pingSent) {
                results.errors.push('Failed to send ping');
                return results;
            }

            const pongResponse = await this.waitForMessage(10000);
            if (!pongResponse || pongResponse.action !== 'pong') {
                results.errors.push('Invalid or missing pong response');
                return results;
            }
            results.details.pingPong = '✅ Success';

            // Test 3: Chat Message
            console.log('🧪 Test 3: Chat Message');
            const testMessage = "Hello Warren! What's your investment advice for beginners?";
            
            const messageSent = await this.sendChatMessage(testMessage);
            if (!messageSent) {
                results.errors.push('Failed to send chat message');
                return results;
            }

            // Should receive acknowledgment
            const ackResponse = await this.waitForMessage(10000);
            if (!ackResponse || ackResponse.action !== 'message_received') {
                results.errors.push('Invalid or missing message acknowledgment');
                return results;
            }
            results.details.messageAck = '✅ Success';

            // Should receive AI response (may take longer)
            console.log('⏳ Waiting for AI response...');
            const aiResponse = await this.waitForMessage(60000);
            if (!aiResponse || aiResponse.action !== 'message_response') {
                results.errors.push('Invalid or missing AI response');
                return results;
            }

            results.details.aiResponse = `✅ Success - ${(aiResponse.content || '').length} chars`;
            results.details.aiContent = (aiResponse.content || '').substring(0, 200) + '...';

            // Test 4: Disconnection
            console.log('🧪 Test 4: Disconnection');
            await this.disconnect();
            results.details.disconnection = '✅ Success';

            results.passed = true;
            console.log('🎉 Basic test completed successfully!');

        } catch (error) {
            results.errors.push(`Unexpected error: ${error.message}`);
            console.error('❌ Test failed:', error.message);
        }

        return results;
    }

    async runMultipleMessages(count = 3) {
        console.log(`🧪 Running Multiple Messages Test (${count} messages)`);
        console.log('=' * 40);
        
        const results = {
            testName: `Multiple Messages Test (${count} messages)`,
            passed: false,
            details: {},
            errors: []
        };

        try {
            const connected = await this.connect();
            if (!connected) {
                results.errors.push('Failed to establish connection');
                return results;
            }

            const startTime = Date.now();
            let messagesSent = 0;
            let acksReceived = 0;

            console.log(`📨 Sending ${count} messages...`);
            
            for (let i = 0; i < count; i++) {
                const testMessage = `Test message #${i + 1}: What are your thoughts on ${['diversification', 'value investing', 'long-term strategies'][i % 3]}?`;
                
                if (await this.sendChatMessage(testMessage)) {
                    messagesSent++;
                    
                    // Wait for acknowledgment
                    const ack = await this.waitForMessage(10000);
                    if (ack && ack.action === 'message_received') {
                        acksReceived++;
                    }
                    
                    // Small delay between messages
                    if (i < count - 1) {
                        await new Promise(resolve => setTimeout(resolve, 1000));
                    }
                } else {
                    console.error(`Failed to send message ${i + 1}`);
                }
            }

            const elapsedTime = (Date.now() - startTime) / 1000;

            results.details = {
                messagesSent,
                acksReceived,
                elapsedTime: `${elapsedTime.toFixed(1)}s`,
                successRate: `${((acksReceived / count) * 100).toFixed(1)}%`
            };

            if (messagesSent === count && acksReceived >= count * 0.8) {
                results.passed = true;
                console.log('🎉 Multiple messages test completed successfully!');
            } else {
                results.errors.push('Multiple messages test did not meet success criteria');
            }

            await this.disconnect();

        } catch (error) {
            results.errors.push(`Unexpected error: ${error.message}`);
            console.error('❌ Multiple messages test failed:', error.message);
        }

        return results;
    }
}

async function runAllTests(websocketUrl, userId = null) {
    const testUserId = userId || `test-user-${Date.now()}`;
    
    console.log('🚀 Starting WebSocket Chat API Tests');
    console.log(`   URL: ${websocketUrl}`);
    console.log(`   User ID: ${testUserId}`);
    console.log('=' * 60);

    const allResults = [];

    // Test 1: Basic functionality
    const tester1 = new WebSocketChatTester(websocketUrl, testUserId);
    const basicResults = await tester1.runBasicTest();
    allResults.push(basicResults);

    await new Promise(resolve => setTimeout(resolve, 2000));

    // Test 2: Multiple messages
    const tester2 = new WebSocketChatTester(websocketUrl, testUserId);
    const multipleResults = await tester2.runMultipleMessages(3);
    allResults.push(multipleResults);

    // Print summary
    console.log('=' * 60);
    console.log('📊 TEST SUMMARY');
    console.log('=' * 60);

    let passedTests = 0;
    const totalTests = allResults.length;

    allResults.forEach(result => {
        const status = result.passed ? '✅ PASSED' : '❌ FAILED';
        console.log(`${result.testName}: ${status}`);

        if (result.passed) {
            passedTests++;
        }

        // Print details
        Object.entries(result.details).forEach(([key, value]) => {
            console.log(`   ${key}: ${value}`);
        });

        // Print errors
        result.errors.forEach(error => {
            console.error(`   ERROR: ${error}`);
        });

        console.log('');
    });

    console.log(`Overall: ${passedTests}/${totalTests} tests passed (${((passedTests / totalTests) * 100).toFixed(1)}%)`);

    return allResults;
}

// Main execution
if (require.main === module) {
    const args = process.argv.slice(2);
    
    if (args.length === 0) {
        console.error('Usage: node websocket_client_node.js <websocket_url> [user_id]');
        console.error('Example: node websocket_client_node.js wss://api123.execute-api.us-east-1.amazonaws.com/dev test-user-123');
        process.exit(1);
    }

    const websocketUrl = args[0];
    const userId = args[1];

    runAllTests(websocketUrl, userId)
        .then(() => {
            console.log('🏁 All tests completed');
            process.exit(0);
        })
        .catch(error => {
            console.error('❌ Test execution failed:', error.message);
            process.exit(1);
        });
}
