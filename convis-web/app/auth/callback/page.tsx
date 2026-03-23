'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

function AuthCallbackPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [message, setMessage] = useState('Processing authentication...');

  const handleCallback = useCallback(async () => {
    try {
      // Get the authorization code or token from URL params
      const code = searchParams.get('code');
      const provider = localStorage.getItem('selectedProvider') || 'twilio';
      const token = localStorage.getItem('token');
      const userStr = localStorage.getItem('user');

      if (!token || !userStr) {
        setStatus('error');
        setMessage('Authentication failed. Please login again.');
        setTimeout(() => router.push('/login'), 2000);
        return;
      }

      const user = JSON.parse(userStr);

      if (!code) {
        setStatus('error');
        setMessage('No authorization code received.');
        setTimeout(() => router.push('/phone-numbers'), 2000);
        return;
      }

      setMessage('Connecting to ' + provider + '...');

      // Send the authorization code to our backend
      const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai';
      const response = await fetch(`${API_URL}/api/phone-numbers/connect`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          provider: provider,
          code: code,
          user_id: user.id,
        }),
      });

      if (response.ok) {
        await response.json();
        setStatus('success');
        setMessage(`Successfully connected to ${provider}! Syncing your phone numbers...`);

        // Store provider credentials if needed
        localStorage.setItem(`${provider}_connected`, 'true');

        // Redirect to phone numbers page after 2 seconds
        setTimeout(() => {
          localStorage.removeItem('selectedProvider');
          router.push('/phone-numbers');
        }, 2000);
      } else {
        const error = await response.json();
        setStatus('error');
        setMessage(error.message || 'Failed to connect to provider.');
        setTimeout(() => router.push('/phone-numbers'), 2000);
      }
    } catch (error) {
      console.error('Callback error:', error);
      setStatus('error');
      setMessage('An error occurred during authentication.');
      setTimeout(() => router.push('/phone-numbers'), 2000);
    }
  }, [router, searchParams]);

  useEffect(() => {
    void handleCallback();
  }, [handleCallback]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary/10 to-primary/5 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-md w-full text-center">
        {status === 'loading' && (
          <>
            <div className="w-20 h-20 bg-gradient-to-br from-primary to-primary/80 rounded-full flex items-center justify-center mx-auto mb-6 animate-pulse">
              <svg className="w-10 h-10 text-white animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-neutral-dark mb-2">
              Connecting...
            </h2>
            <p className="text-neutral-mid">
              {message}
            </p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="w-20 h-20 bg-gradient-to-br from-green-500 to-green-600 rounded-full flex items-center justify-center mx-auto mb-6">
              <svg className="w-10 h-10 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-neutral-dark mb-2">
              Success!
            </h2>
            <p className="text-neutral-mid">
              {message}
            </p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="w-20 h-20 bg-gradient-to-br from-red-500 to-red-600 rounded-full flex items-center justify-center mx-auto mb-6">
              <svg className="w-10 h-10 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-neutral-dark mb-2">
              Connection Failed
            </h2>
            <p className="text-neutral-mid">
              {message}
            </p>
          </>
        )}
      </div>
    </div>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading...</p>
        </div>
      </div>
    }>
      <AuthCallbackPageContent />
    </Suspense>
  );
}
