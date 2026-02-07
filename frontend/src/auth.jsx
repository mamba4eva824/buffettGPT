import React, { createContext, useContext, useEffect, useState, useRef } from 'react';
import { LogIn, LogOut, User } from 'lucide-react';
import logger from './utils/logger';

// Auth Context
const AuthContext = createContext();

// Environment configuration
const AUTH_CONFIG = {
  GOOGLE_CLIENT_ID: import.meta.env.VITE_GOOGLE_CLIENT_ID,
  API_BASE_URL: import.meta.env.VITE_REST_API_URL || "https://4onfe7pbpc.execute-api.us-east-1.amazonaws.com/dev",
  // Development mode - allow manual token input for testing
  ENABLE_DEV_MODE: import.meta.env.VITE_ENVIRONMENT === 'development'
};

// Local storage keys
const LS_AUTH_KEYS = {
  user: "chat.auth.user",
  token: "chat.auth.token",
  expiresAt: "chat.auth.expiresAt"
};

// Auth Provider Component
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);

  // Initialize auth state from localStorage
  useEffect(() => {
    try {
      const storedUser = localStorage.getItem(LS_AUTH_KEYS.user);
      const storedToken = localStorage.getItem(LS_AUTH_KEYS.token);
      const expiresAt = localStorage.getItem(LS_AUTH_KEYS.expiresAt);

      if (storedUser && storedToken && expiresAt) {
        const expiry = new Date(expiresAt);
        if (expiry > new Date()) {
          setUser(JSON.parse(storedUser));
          setToken(storedToken);
        } else {
          // Token expired, clear storage
          clearAuthStorage();
        }
      }
    } catch (error) {
      logger.error('Error loading auth state:', error);
      clearAuthStorage();
    } finally {
      setLoading(false);
    }
  }, []);

  const clearAuthStorage = () => {
    localStorage.removeItem(LS_AUTH_KEYS.user);
    localStorage.removeItem(LS_AUTH_KEYS.token);
    localStorage.removeItem(LS_AUTH_KEYS.expiresAt);
  };

  const handleGoogleCallback = async (googleToken) => {
    try {
      setLoading(true);

      // Send Google token to our backend for verification
      const response = await fetch(`${AUTH_CONFIG.API_BASE_URL}/auth/callback`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ credential: googleToken })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Authentication failed');
      }

      const authData = await response.json();

      // Store user data and JWT token
      const userData = authData.user;
      const jwtToken = authData.token;
      // Calculate expiration time from expires_in (seconds from now)
      const expiresAt = new Date(Date.now() + authData.expires_in * 1000).toISOString();

      setUser(userData);
      setToken(jwtToken);

      // Persist to localStorage
      localStorage.setItem(LS_AUTH_KEYS.user, JSON.stringify(userData));
      localStorage.setItem(LS_AUTH_KEYS.token, jwtToken);
      localStorage.setItem(LS_AUTH_KEYS.expiresAt, expiresAt);

      console.log('Authentication successful:', userData);
      return { success: true };
      
    } catch (error) {
      console.error('Authentication error:', error);
      return { success: false, error: error.message };
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    setUser(null);
    setToken(null);
    clearAuthStorage();
    
    // Sign out from Google
    if (window.google) {
      window.google.accounts.id.disableAutoSelect();
    }
  };

  const value = {
    user,
    token,
    loading,
    isAuthenticated: !!user && !!token,
    handleGoogleCallback,
    logout
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

// Hook to use auth context
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

// Google Login Button Component
export function GoogleLoginButton({ className = "" }) {
  const { handleGoogleCallback, loading } = useAuth();
  const [isGoogleLoaded, setIsGoogleLoaded] = useState(false);
  const buttonRenderedRef = useRef(false);

  useEffect(() => {
    // Check if Google Identity Services is loaded
    const checkGoogle = () => {
      if (window.google && window.google.accounts && window.google.accounts.id) {
        setIsGoogleLoaded(true);
        
        // Initialize Google Sign-In
        console.log('Initializing Google Sign-In with client ID:', AUTH_CONFIG.GOOGLE_CLIENT_ID);
        try {
          window.google.accounts.id.initialize({
            client_id: AUTH_CONFIG.GOOGLE_CLIENT_ID,
            callback: async (response) => {
              console.log('Google Sign-In callback received:', response);
              const result = await handleGoogleCallback(response.credential);
              if (!result.success) {
                alert(`Login failed: ${result.error}`);
              }
            },
            auto_select: false,
            cancel_on_tap_outside: true,
            use_fedcm_for_prompt: true
          });
          console.log('Google Sign-In initialized successfully');

          // Render the official Google Sign-In button once
          if (!buttonRenderedRef.current) {
            const buttonEl = document.getElementById('gsi-button');
            if (buttonEl) {
              window.google.accounts.id.renderButton(buttonEl, {
                theme: 'outline',
                size: 'large',
                text: 'signin_with',
                shape: 'rectangular'
              });
              buttonRenderedRef.current = true;
            }
          }
        } catch (error) {
          console.error('Error initializing Google Sign-In:', error);
        }
      } else {
        // Retry after a short delay
        setTimeout(checkGoogle, 100);
      }
    };

    checkGoogle();
  }, [handleGoogleCallback]);

  // Using the official GSI button only; no custom prompt button.

  if (!isGoogleLoaded) {
    return (
      <div className={`flex flex-col gap-2 ${className}`}>
        <div id="gsi-button" />
        <button 
          disabled 
          className="flex items-center gap-2 px-4 py-2 text-sm text-sand-400"
        >
          <LogIn size={16} />
          Loading...
        </button>
      </div>
    );
  }

  return (
    <div className={`flex items-center ${className}`}>
      <div id="gsi-button" />
    </div>
  );
}

// User Profile Display Component  
export function UserProfile({ className = "" }) {
  const { user, logout, loading } = useAuth();

  if (!user) return null;

  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <div className="flex items-center gap-2">
        {user.picture ? (
          <img 
            src={user.picture} 
            alt={user.name} 
            className="w-8 h-8 rounded-full"
          />
        ) : (
          <div className="w-8 h-8 bg-sand-200 rounded-full flex items-center justify-center">
            <User size={16} />
          </div>
        )}
        <div className="text-sm">
          <div className="font-medium text-sand-900">{user.name}</div>
          <div className="text-sand-500">{user.email}</div>
        </div>
      </div>
      <button
        onClick={logout}
        disabled={loading}
        className="flex items-center gap-1 px-3 py-1 text-xs text-sand-600 hover:text-sand-800 border border-sand-200 rounded hover:bg-sand-50 transition-colors"
      >
        <LogOut size={12} />
        Sign out
      </button>
    </div>
  );
}

// Development Test Component for Manual Token Input
export function DevTokenTester({ className = "" }) {
  const { handleGoogleCallback, loading } = useAuth();
  const [testToken, setTestToken] = useState('');
  const [showTester, setShowTester] = useState(false);

  const handleTestToken = async () => {
    if (!testToken.trim()) {
      alert('Please enter a Google OAuth token');
      return;
    }
    
    const result = await handleGoogleCallback(testToken);
    if (!result.success) {
      alert(`Test failed: ${result.error}`);
    } else {
      alert('Test successful!');
      setShowTester(false);
      setTestToken('');
    }
  };

  if (!AUTH_CONFIG.ENABLE_DEV_MODE) return null;

  return (
    <div className={className}>
      {!showTester ? (
        <button 
          onClick={() => setShowTester(true)}
          className="px-3 py-1 text-xs bg-yellow-100 text-yellow-800 rounded hover:bg-yellow-200"
        >
          🧪 Dev Test
        </button>
      ) : (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-sand-50 p-6 rounded-lg max-w-md w-full mx-4">
            <h3 className="text-lg font-medium mb-4">Test OAuth Token</h3>
            <p className="text-sm text-sand-600 mb-4">
              Get a Google OAuth token from{' '}
              <a 
                href="https://developers.google.com/oauthplayground" 
                target="_blank" 
                rel="noopener noreferrer"
                className="text-blue-600 underline"
              >
                OAuth Playground
              </a>
            </p>
            <textarea
              value={testToken}
              onChange={(e) => setTestToken(e.target.value)}
              placeholder="Paste Google OAuth token here..."
              className="w-full h-32 p-3 border border-sand-300 rounded resize-none text-sm"
            />
            <div className="flex gap-2 mt-4">
              <button 
                onClick={handleTestToken}
                disabled={loading || !testToken.trim()}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
              >
                {loading ? 'Testing...' : 'Test Token'}
              </button>
              <button 
                onClick={() => {setShowTester(false); setTestToken('');}}
                className="px-4 py-2 bg-sand-300 text-sand-700 rounded hover:bg-sand-400"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Auth Button - shows login or user profile based on auth state
export function AuthButton({ className = "" }) {
  const { isAuthenticated } = useAuth();

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {isAuthenticated ? (
        <UserProfile />
      ) : (
        <>
          <GoogleLoginButton />
          <DevTokenTester />
        </>
      )}
    </div>
  );
}