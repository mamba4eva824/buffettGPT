#!/usr/bin/env node

/**
 * Test API Connection Script
 * Verifies that the backend APIs are accessible and CORS is configured correctly
 */

import dotenv from 'dotenv';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import fs from 'fs';

// Load environment variables
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Load .env.local first (highest priority), then .env.development
if (fs.existsSync(join(__dirname, '.env.local'))) {
  dotenv.config({ path: join(__dirname, '.env.local') });
}
dotenv.config({ path: join(__dirname, '.env.development') });

const REST_API_URL = process.env.VITE_REST_API_URL;
const WEBSOCKET_URL = process.env.VITE_WEBSOCKET_URL;

console.log('🔍 Testing API Connections...\n');
console.log('REST API URL:', REST_API_URL || '❌ Not configured');
console.log('WebSocket URL:', WEBSOCKET_URL || '❌ Not configured');
console.log('-----------------------------------\n');

// Test REST API health endpoint
async function testRestApi() {
  if (!REST_API_URL) {
    console.log('❌ REST API URL not configured. Please set VITE_REST_API_URL in .env.local');
    return false;
  }

  console.log('📡 Testing REST API...');

  try {
    // Test health endpoint (should work without auth)
    const healthUrl = `${REST_API_URL}/health`;
    console.log(`   Checking: ${healthUrl}`);

    const response = await fetch(healthUrl, {
      method: 'GET',
      headers: {
        'Origin': 'http://localhost:5173',
        'Content-Type': 'application/json'
      }
    });

    if (response.ok) {
      const data = await response.json();
      console.log('   ✅ REST API is accessible');
      console.log('   Response:', JSON.stringify(data, null, 2));

      // Check CORS headers
      const corsHeaders = {
        'access-control-allow-origin': response.headers.get('access-control-allow-origin'),
        'access-control-allow-credentials': response.headers.get('access-control-allow-credentials'),
      };

      console.log('   CORS Headers:', corsHeaders);

      if (corsHeaders['access-control-allow-origin']) {
        console.log('   ✅ CORS is configured');
      } else {
        console.log('   ⚠️  CORS headers not present - may need configuration');
      }

      return true;
    } else {
      console.log(`   ❌ REST API returned status: ${response.status}`);
      const text = await response.text();
      console.log('   Response:', text);
      return false;
    }
  } catch (error) {
    console.log('   ❌ REST API connection failed');
    console.log('   Error:', error.message);
    return false;
  }
}

// Test WebSocket connection
async function testWebSocket() {
  if (!WEBSOCKET_URL) {
    console.log('❌ WebSocket URL not configured. Please set VITE_WEBSOCKET_URL in .env.local');
    return false;
  }

  console.log('\n🔌 Testing WebSocket...');
  console.log(`   Connecting to: ${WEBSOCKET_URL}`);

  return new Promise((resolve) => {
    try {
      // Note: WebSocket in Node.js requires the 'ws' package
      // This is just for demonstration - actual testing should be done in browser
      console.log('   ⚠️  WebSocket testing requires browser environment');
      console.log('   Please test WebSocket connection in the browser console:');
      console.log(`   new WebSocket('${WEBSOCKET_URL}')`);
      resolve(true);
    } catch (error) {
      console.log('   ❌ WebSocket test failed');
      console.log('   Error:', error.message);
      resolve(false);
    }
  });
}

// Test conversations API endpoint
async function testConversationsApi() {
  if (!REST_API_URL) {
    return false;
  }

  console.log('\n📚 Testing Conversations API...');

  try {
    const conversationsUrl = `${REST_API_URL}/conversations`;
    console.log(`   Checking: ${conversationsUrl}`);

    // This will likely fail without auth, but we can check if the endpoint exists
    const response = await fetch(conversationsUrl, {
      method: 'GET',
      headers: {
        'Origin': 'http://localhost:5173',
        'Content-Type': 'application/json'
      }
    });

    if (response.status === 401 || response.status === 403) {
      console.log('   ✅ Conversations endpoint exists (requires authentication)');
      return true;
    } else if (response.ok) {
      console.log('   ✅ Conversations endpoint is accessible');
      return true;
    } else if (response.status === 404) {
      console.log('   ⚠️  Conversations endpoint not found - may not be deployed yet');
      return false;
    } else {
      console.log(`   ⚠️  Unexpected status: ${response.status}`);
      return false;
    }
  } catch (error) {
    console.log('   ❌ Conversations API test failed');
    console.log('   Error:', error.message);
    return false;
  }
}

// Run all tests
async function runTests() {
  const results = {
    restApi: await testRestApi(),
    webSocket: await testWebSocket(),
    conversations: await testConversationsApi()
  };

  console.log('\n===================================');
  console.log('📊 Test Summary:');
  console.log('-----------------------------------');
  console.log(`REST API:        ${results.restApi ? '✅ Pass' : '❌ Fail'}`);
  console.log(`WebSocket:       ${results.webSocket ? '⚠️  Manual test needed' : '❌ Fail'}`);
  console.log(`Conversations:   ${results.conversations ? '✅ Pass' : '⚠️  Not ready'}`);
  console.log('===================================\n');

  if (!results.restApi) {
    console.log('💡 Next Steps:');
    console.log('1. Ensure your backend is deployed (terraform apply)');
    console.log('2. Update .env.local with correct API URLs');
    console.log('3. Check API Gateway CORS configuration');
  }

  console.log('\n📝 To start the development server:');
  console.log('   npm run dev\n');
}

// Run the tests
runTests().catch(console.error);