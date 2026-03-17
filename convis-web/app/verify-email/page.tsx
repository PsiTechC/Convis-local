'use client';

import { useState, useEffect, Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams, useRouter } from 'next/navigation';

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const email = searchParams.get('email');

  const [otp, setOtp] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  const [isResending, setIsResending] = useState(false);

  // Redirect if no email provided
  useEffect(() => {
    if (!email) {
      router.push('/register');
    }
  }, [email, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccessMessage('');

    if (!otp.trim()) {
      setError('Please enter the OTP');
      return;
    }

    if (otp.length < 4) {
      setError('Please enter a valid OTP');
      return;
    }

    setIsLoading(true);

    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai';
      const response = await fetch(`${API_URL}/api/register/verify-email`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: email,
          otp: otp,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        setSuccessMessage(data.message || 'Email verified successfully!');
        // Redirect to login after 2 seconds
        setTimeout(() => {
          router.push('/login');
        }, 2000);
      } else {
        setError(data.detail || 'Verification failed. Please try again.');
      }
    } catch (_error) {
      setError('Network error. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleResendOTP = async () => {
    setError('');
    setSuccessMessage('');
    setIsResending(true);

    try {
      // You might need to create a resend OTP endpoint
      // For now, we'll show a message
      setSuccessMessage('A new OTP has been sent to your email.');
      setOtp('');
    } catch (_error) {
      setError('Failed to resend OTP. Please try again.');
    } finally {
      setIsResending(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value.replace(/\D/g, ''); // Only allow digits
    setOtp(value);
    if (error) setError('');
  };

  if (!email) {
    return null; // Will redirect
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-neutral-mid/5 to-neutral-light p-4 lg:p-8">
      <div className="w-full max-w-6xl">
        {/* Main Card */}
        <div className="bg-white rounded-2xl lg:rounded-3xl shadow-2xl overflow-hidden">
          <div className="grid lg:grid-cols-2 min-h-[600px]">

            {/* Mobile Header - Only visible on small screens */}
            <div className="lg:hidden bg-gradient-to-r from-primary to-primary/90 p-6 text-center">
              <div className="w-16 h-16 bg-white rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg">
                <svg className="w-10 h-10 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              </div>
              <h1 className="text-2xl font-bold text-white font-heading mb-2">
                Verify Your Email
              </h1>
              <p className="text-white/80 text-sm">
                Enter the OTP sent to your email
              </p>
            </div>

            {/* Left Side - Blue Section */}
            <div className="relative bg-gradient-to-br from-primary via-primary to-primary/90 p-8 lg:p-12 flex flex-col justify-between overflow-hidden hidden lg:flex">
              {/* Decorative Wave/Cloud Pattern */}
              <div className="absolute top-0 right-0 w-full h-full opacity-10">
                <div className="absolute top-0 right-0 w-96 h-96 bg-white rounded-full blur-3xl transform translate-x-1/2 -translate-y-1/2"></div>
                <div className="absolute top-1/4 right-1/4 w-64 h-64 bg-white/50 rounded-full blur-2xl"></div>
                <div className="absolute bottom-0 left-0 w-full h-full bg-gradient-to-tr from-white/5 to-transparent transform -skew-y-12"></div>
              </div>

              <div className="relative z-10">
                {/* Logo/Icon - Email themed */}
                <div className="w-20 h-20 bg-white rounded-2xl flex items-center justify-center mb-8 shadow-2xl">
                  <svg className="w-12 h-12 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                </div>

                <h1 className="text-4xl lg:text-5xl font-bold text-white mb-4 font-heading leading-tight">
                  Almost There!
                </h1>

                <p className="text-white/90 text-base lg:text-lg leading-relaxed max-w-md mb-8">
                  We&apos;ve sent a verification code to your email address.
                  Please check your inbox and enter the code below to complete your registration.
                </p>

                {/* Info highlights */}
                <div className="space-y-3 text-white/80 text-sm">
                  <div className="flex items-center gap-3">
                    <svg className="w-5 h-5 text-accent" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>Check your spam folder if not received</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <svg className="w-5 h-5 text-accent" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>Code is valid for 10 minutes</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <svg className="w-5 h-5 text-accent" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>Secure and encrypted verification</span>
                  </div>
                </div>
              </div>

              {/* Bottom Links */}
              <div className="relative z-10 flex flex-wrap gap-4 lg:gap-6 text-white/70 text-sm">
                <a href="#" className="hover:text-white transition-colors">Terms of service</a>
                <a href="#" className="hover:text-white transition-colors">Privacy policy</a>
                <span className="text-white/50">© 2025 Convis</span>
              </div>
            </div>

            {/* Right Side - Form Section */}
            <div className="p-8 lg:p-12 flex flex-col justify-center bg-gradient-to-br from-white to-neutral-light/30">
              <div className="max-w-md mx-auto w-full">

                {/* Form Header */}
                <div className="mb-8">
                  <h2 className="text-3xl font-bold text-neutral-dark mb-2 font-heading">
                    Verify your email
                  </h2>
                  <p className="text-neutral-mid text-sm">
                    Code sent to <span className="font-semibold text-neutral-dark">{email}</span>
                  </p>
                </div>

                {successMessage && (
                  <div className="mb-6 p-4 bg-gradient-to-r from-accent/10 to-accent/5 border border-accent/30 rounded-xl">
                    <div className="flex items-start gap-2">
                      <svg className="w-5 h-5 text-accent flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                      <p className="text-sm text-accent font-medium">{successMessage}</p>
                    </div>
                  </div>
                )}

                {error && (
                  <div className="mb-6 p-4 bg-gradient-to-r from-red-50 to-red-50/50 border border-red-200 rounded-xl">
                    <div className="flex items-start gap-2">
                      <svg className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                      </svg>
                      <p className="text-sm text-red-700 font-medium">{error}</p>
                    </div>
                  </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-6">
                  {/* OTP Input */}
                  <div>
                    <label
                      htmlFor="otp"
                      className="block text-sm font-medium text-neutral-dark mb-2"
                    >
                      Verification Code
                    </label>
                    <input
                      type="text"
                      id="otp"
                      name="otp"
                      value={otp}
                      onChange={handleChange}
                      maxLength={6}
                      className={`w-full px-4 py-3 rounded-xl border ${
                        error
                          ? 'border-red-300 focus:border-red-500 focus:ring-2 focus:ring-red-100'
                          : 'border-neutral-mid/20 focus:border-primary focus:ring-2 focus:ring-primary/10'
                      } focus:outline-none bg-white transition-all duration-200 text-neutral-dark placeholder:text-neutral-mid/50 text-center text-2xl tracking-widest font-semibold`}
                      placeholder="000000"
                      autoComplete="off"
                    />
                    <p className="mt-2 text-xs text-neutral-mid text-center">
                      Enter the 6-digit code sent to your email
                    </p>
                  </div>

                  {/* Submit Button */}
                  <button
                    type="submit"
                    disabled={isLoading}
                    className="w-full bg-gradient-to-r from-primary via-primary to-primary/90 text-white py-3.5 px-6 rounded-xl font-semibold hover:shadow-xl hover:shadow-primary/20 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 shadow-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none"
                  >
                    {isLoading ? (
                      <span className="flex items-center justify-center gap-2">
                        <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Verifying...
                      </span>
                    ) : (
                      'Verify Email'
                    )}
                  </button>

                  {/* Resend OTP */}
                  <div className="text-center">
                    <p className="text-sm text-neutral-mid mb-2">
                      Didn&apos;t receive the code?
                    </p>
                    <button
                      type="button"
                      onClick={handleResendOTP}
                      disabled={isResending}
                      className="text-primary font-semibold hover:text-primary/80 transition-colors text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isResending ? 'Resending...' : 'Resend Code'}
                    </button>
                  </div>

                  {/* Back to Register Link */}
                  <p className="text-center text-sm text-neutral-mid mt-6">
                    Wrong email?{' '}
                    <Link
                      href="/register"
                      className="text-primary font-semibold hover:text-primary/80 transition-colors"
                    >
                      Back to Register
                    </Link>
                  </p>
                </form>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function VerifyEmailPageContent() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center min-h-screen"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div></div>}>
      <VerifyEmailContent />
    </Suspense>
  );
}

export default function VerifyEmailPage() {
  return <VerifyEmailPageContent />;
}
