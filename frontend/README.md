# Warren Buffett Chat AI Frontend

A React + Tailwind CSS frontend for the Warren Buffett Chat API, designed to connect to your AWS infrastructure.

## Features

- 🎨 Modern UI with Tailwind CSS
- 🔌 WebSocket integration for real-time chat
- 📱 Responsive design
- 💾 Local session management
- 🔧 Easy configuration via Settings panel

## Quick Start

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Start the development server:**
   ```bash
   npm run dev
   ```

3. **Open your browser to:** `http://localhost:3000`

## Configuration

### Automatic Configuration (Recommended)

The app is pre-configured with your API endpoints via environment variables:

- **Development**: Uses `.env.development` with your AWS dev APIs
- **Production**: Uses `.env.production` for production deployment
- **Local Override**: Users can still manually override URLs in Settings if needed

### Manual Configuration (Optional)

If you need to override the defaults, click the "Settings" button to configure:

- **WebSocket URL**: Your AWS API Gateway WebSocket endpoint
- **REST Base URL**: Your AWS API Gateway REST endpoint for chat history

### Environment Files

```bash
# .env.development (already configured)
VITE_WEBSOCKET_URL=wss://52x14spfai.execute-api.us-east-1.amazonaws.com/dev
VITE_REST_API_URL=https://4onfe7pbpc.execute-api.us-east-1.amazonaws.com/dev

# .env.production (update when deploying to prod)
VITE_WEBSOCKET_URL=wss://your-prod-websocket-id.execute-api.region.amazonaws.com/prod
VITE_REST_API_URL=https://your-prod-http-api-id.execute-api.region.amazonaws.com/prod
```

## Development Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build locally

## Project Structure

```
frontend/
├── src/
│   ├── App.jsx          # Main application component
│   ├── main.jsx         # React entry point
│   └── index.css        # Global styles with Tailwind
├── index.html           # HTML template
├── package.json         # Dependencies and scripts
├── vite.config.js       # Vite configuration
├── tailwind.config.js   # Tailwind CSS configuration
└── postcss.config.js    # PostCSS configuration
```

## UI Features

- **Chat Interface**: Clean, modern chat bubbles with timestamps
- **Session Management**: Automatic session tracking and history
- **Connection Status**: Real-time WebSocket connection indicator
- **Settings Panel**: Easy configuration for API endpoints
- **Responsive Design**: Works on desktop and mobile devices

## Integration with AWS Backend

This frontend is designed to work with your existing AWS infrastructure:

- **WebSocket API**: Connects to your API Gateway WebSocket for real-time messaging
- **REST API**: Fetches chat history via HTTP endpoints
- **Session Management**: Automatically handles session creation and tracking

## Customization

The UI can be easily customized by modifying:

- **Colors**: Update the Tailwind color classes in `App.jsx`
- **Layout**: Modify the component structure and sizing
- **Branding**: Change the app name and styling to match your brand

## Production Deployment

To deploy to production:

1. Build the app: `npm run build`
2. Deploy the `dist/` folder to your preferred hosting service (S3, Netlify, Vercel, etc.)
3. Configure your CDN/hosting to route API calls to your AWS API Gateway

## Notes

- The app stores settings in localStorage for convenience
- WebSocket connections are automatically managed
- The UI expects specific message formats from your backend (see App.jsx comments)
- Error handling and reconnection logic is built-in
