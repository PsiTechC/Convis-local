'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { DotLottieReact } from '@lottiefiles/dotlottie-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai';

type Step = 'email' | 'verify' | 'reset';

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>('email');
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');

  // Step 1: Send OTP
  const handleSendOTP = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});
    setSuccessMessage('');

    if (!email.trim()) {
      setErrors({ email: 'Email is required' });
      return;
    }

    if (!/\S+@\S+\.\S+/.test(email)) {
      setErrors({ email: 'Email is invalid' });
      return;
    }

    setIsLoading(true);

    try {
      const response = await fetch(`${API_URL}/api/forgot_password/send-otp`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email }),
      });

      const data = await response.json();

      if (response.ok) {
        setSuccessMessage('OTP sent to your email. Please check your inbox.');
        setStep('verify');
      } else {
        setErrors({ submit: data.detail || 'Failed to send OTP. Please try again.' });
      }
    } catch (_error) {
      setErrors({ submit: 'Network error. Please try again.' });
    } finally {
      setIsLoading(false);
    }
  };

  // Step 2: Verify OTP
  const handleVerifyOTP = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});
    setSuccessMessage('');

    if (!otp.trim()) {
      setErrors({ otp: 'OTP is required' });
      return;
    }

    setIsLoading(true);

    try {
      const response = await fetch(`${API_URL}/api/forgot_password/verify-otp`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, otp }),
      });

      const data = await response.json();

      if (response.ok) {
        setSuccessMessage('OTP verified successfully. Please enter your new password.');
        setStep('reset');
      } else {
        setErrors({ submit: data.detail || 'Invalid OTP. Please try again.' });
      }
    } catch (_error) {
      setErrors({ submit: 'Network error. Please try again.' });
    } finally {
      setIsLoading(false);
    }
  };

  // Step 3: Reset Password
  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});
    setSuccessMessage('');

    const newErrors: Record<string, string> = {};

    if (!newPassword) {
      newErrors.newPassword = 'Password is required';
    } else if (newPassword.length < 8) {
      newErrors.newPassword = 'Password must be at least 8 characters';
    }

    if (!confirmPassword) {
      newErrors.confirmPassword = 'Please confirm your password';
    } else if (newPassword !== confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    setIsLoading(true);

    try {
      const response = await fetch(`${API_URL}/api/forgot_password/reset-password`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, newPassword }),
      });

      const data = await response.json();

      if (response.ok) {
        setSuccessMessage('Password reset successful! Redirecting to login...');
        setTimeout(() => {
          router.push('/login');
        }, 2000);
      } else {
        setErrors({ submit: data.detail || 'Failed to reset password. Please try again.' });
      }
    } catch (_error) {
      setErrors({ submit: 'Network error. Please try again.' });
    } finally {
      setIsLoading(false);
    }
  };

  const getStepTitle = () => {
    switch (step) {
      case 'email':
        return 'Forgot Password?';
      case 'verify':
        return 'Verify OTP';
      case 'reset':
        return 'Reset Password';
    }
  };

  const getStepDescription = () => {
    switch (step) {
      case 'email':
        return 'Enter your email address and we will send you an OTP to reset your password';
      case 'verify':
        return 'Enter the OTP sent to your email address';
      case 'reset':
        return 'Enter your new password';
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-neutral-mid/5 to-neutral-light p-4 lg:p-8">
      <div className="w-full max-w-6xl">
        <div className="bg-white rounded-2xl lg:rounded-3xl shadow-2xl overflow-hidden">
          <div className="grid lg:grid-cols-2 min-h-[600px]">

            {/* Mobile Header - Only visible on small screens */}
            <div className="lg:hidden bg-gradient-to-r from-primary to-primary/90 p-6 text-center">
              <div className="w-16 h-16 bg-white rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg">
                <DotLottieReact
                  src="/microphone-animation.lottie"
                  loop
                  autoplay
                  style={{ width: '40px', height: '40px' }}
                />
              </div>
              <h1 className="text-2xl font-bold text-white font-heading mb-2">
                Reset Your Password
              </h1>
              <p className="text-white/80 text-sm">
                We will help you recover your account
              </p>
            </div>

            {/* Left Side - Blue Section */}
            <div className="relative bg-gradient-to-br from-primary via-primary to-primary/90 p-8 lg:p-12 flex flex-col justify-between overflow-hidden hidden lg:flex">
              <div className="absolute top-0 right-0 w-full h-full opacity-10">
                <div className="absolute top-0 right-0 w-96 h-96 bg-white rounded-full blur-3xl transform translate-x-1/2 -translate-y-1/2"></div>
                <div className="absolute top-1/4 right-1/4 w-64 h-64 bg-white/50 rounded-full blur-2xl"></div>
                <div className="absolute bottom-0 left-0 w-full h-full bg-gradient-to-tr from-white/5 to-transparent transform -skew-y-12"></div>
              </div>

              <div className="relative z-10">
                <div className="w-20 h-20 bg-white rounded-2xl flex items-center justify-center mb-8 shadow-2xl">
                  <DotLottieReact
                    src="/microphone-animation.lottie"
                    loop
                    autoplay
                    style={{ width: '48px', height: '48px' }}
                  />
                </div>

                <h1 className="text-4xl lg:text-5xl font-bold text-white mb-4 font-heading leading-tight">
                  Password Recovery
                </h1>

                <p className="text-white/90 text-base lg:text-lg leading-relaxed max-w-md mb-8">
                  Follow the simple steps to recover your account and get back to managing your AI voice assistants.
                </p>

                {/* Step indicators */}
                <div className="space-y-3 text-white/80 text-sm">
                  <div className={`flex items-center gap-3 ${step === 'email' ? 'text-accent font-semibold' : ''}`}>
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center ${step === 'email' ? 'bg-accent text-white' : 'bg-white/20'}`}>
                      1
                    </div>
                    <span>Enter your email address</span>
                  </div>
                  <div className={`flex items-center gap-3 ${step === 'verify' ? 'text-accent font-semibold' : ''}`}>
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center ${step === 'verify' ? 'bg-accent text-white' : 'bg-white/20'}`}>
                      2
                    </div>
                    <span>Verify OTP from email</span>
                  </div>
                  <div className={`flex items-center gap-3 ${step === 'reset' ? 'text-accent font-semibold' : ''}`}>
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center ${step === 'reset' ? 'bg-accent text-white' : 'bg-white/20'}`}>
                      3
                    </div>
                    <span>Set new password</span>
                  </div>
                </div>
              </div>

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
                    {getStepTitle()}
                  </h2>
                  <p className="text-neutral-mid text-sm">
                    {getStepDescription()}
                  </p>
                </div>

                {/* Success Message */}
                {successMessage && (
                  <div className="mb-6 p-4 bg-gradient-to-r from-green-50 to-green-50/50 border border-green-200 rounded-xl">
                    <div className="flex items-start gap-2">
                      <svg className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                      <p className="text-sm text-green-700 font-medium">{successMessage}</p>
                    </div>
                  </div>
                )}

                {/* Error Message */}
                {errors.submit && (
                  <div className="mb-6 p-4 bg-gradient-to-r from-red-50 to-red-50/50 border border-red-200 rounded-xl">
                    <div className="flex items-start gap-2">
                      <svg className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                      </svg>
                      <p className="text-sm text-red-700 font-medium">{errors.submit}</p>
                    </div>
                  </div>
                )}

                {/* Step 1: Email Form */}
                {step === 'email' && (
                  <form onSubmit={handleSendOTP} className="space-y-5">
                    <div>
                      <label
                        htmlFor="email"
                        className="block text-sm font-medium text-neutral-dark mb-2"
                      >
                        E-mail Address
                      </label>
                      <input
                        type="email"
                        id="email"
                        name="email"
                        value={email}
                        onChange={(e) => {
                          setEmail(e.target.value);
                          if (errors.email) {
                            setErrors((prev) => {
                              const newErrors = { ...prev };
                              delete newErrors.email;
                              return newErrors;
                            });
                          }
                        }}
                        className={`w-full px-4 py-3 rounded-xl border ${
                          errors.email
                            ? 'border-red-300 focus:border-red-500 focus:ring-2 focus:ring-red-100'
                            : 'border-neutral-mid/20 focus:border-primary focus:ring-2 focus:ring-primary/10'
                        } focus:outline-none bg-white transition-all duration-200 text-neutral-dark placeholder:text-neutral-mid/50`}
                        placeholder="you@company.com"
                      />
                      {errors.email && (
                        <p className="mt-1.5 text-xs text-red-600">{errors.email}</p>
                      )}
                    </div>

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
                          Sending OTP...
                        </span>
                      ) : (
                        'Send OTP'
                      )}
                    </button>

                    <p className="text-center text-sm text-neutral-mid mt-6">
                      Remember your password?{' '}
                      <Link
                        href="/login"
                        className="text-primary font-semibold hover:text-primary/80 transition-colors"
                      >
                        Sign In
                      </Link>
                    </p>
                  </form>
                )}

                {/* Step 2: Verify OTP Form */}
                {step === 'verify' && (
                  <form onSubmit={handleVerifyOTP} className="space-y-5">
                    <div>
                      <label
                        htmlFor="otp"
                        className="block text-sm font-medium text-neutral-dark mb-2"
                      >
                        Enter OTP
                      </label>
                      <input
                        type="text"
                        id="otp"
                        name="otp"
                        value={otp}
                        onChange={(e) => {
                          setOtp(e.target.value);
                          if (errors.otp) {
                            setErrors((prev) => {
                              const newErrors = { ...prev };
                              delete newErrors.otp;
                              return newErrors;
                            });
                          }
                        }}
                        className={`w-full px-4 py-3 rounded-xl border ${
                          errors.otp
                            ? 'border-red-300 focus:border-red-500 focus:ring-2 focus:ring-red-100'
                            : 'border-neutral-mid/20 focus:border-primary focus:ring-2 focus:ring-primary/10'
                        } focus:outline-none bg-white transition-all duration-200 text-neutral-dark placeholder:text-neutral-mid/50`}
                        placeholder="Enter 6-digit OTP"
                        maxLength={6}
                      />
                      {errors.otp && (
                        <p className="mt-1.5 text-xs text-red-600">{errors.otp}</p>
                      )}
                      <p className="mt-2 text-xs text-neutral-mid">
                        OTP sent to: <span className="font-medium text-neutral-dark">{email}</span>
                      </p>
                    </div>

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
                        'Verify OTP'
                      )}
                    </button>

                    <div className="flex justify-between items-center text-sm">
                      <button
                        type="button"
                        onClick={() => setStep('email')}
                        className="text-neutral-mid hover:text-primary transition-colors"
                      >
                        Change email
                      </button>
                      <button
                        type="button"
                        onClick={handleSendOTP}
                        disabled={isLoading}
                        className="text-primary hover:text-primary/80 transition-colors font-medium disabled:opacity-50"
                      >
                        Resend OTP
                      </button>
                    </div>
                  </form>
                )}

                {/* Step 3: Reset Password Form */}
                {step === 'reset' && (
                  <form onSubmit={handleResetPassword} className="space-y-5">
                    <div>
                      <label
                        htmlFor="newPassword"
                        className="block text-sm font-medium text-neutral-dark mb-2"
                      >
                        New Password
                      </label>
                      <div className="relative">
                        <input
                          type={showNewPassword ? 'text' : 'password'}
                          id="newPassword"
                          name="newPassword"
                          value={newPassword}
                          onChange={(e) => {
                            setNewPassword(e.target.value);
                            if (errors.newPassword) {
                              setErrors((prev) => {
                                const newErrors = { ...prev };
                                delete newErrors.newPassword;
                                return newErrors;
                              });
                            }
                          }}
                          className={`w-full px-4 py-3 rounded-xl border ${
                            errors.newPassword
                              ? 'border-red-300 focus:border-red-500 focus:ring-2 focus:ring-red-100'
                              : 'border-neutral-mid/20 focus:border-primary focus:ring-2 focus:ring-primary/10'
                          } focus:outline-none bg-white transition-all duration-200 text-neutral-dark placeholder:text-neutral-mid/50 pr-11`}
                          placeholder="Enter new password"
                        />
                        <button
                          type="button"
                          onClick={() => setShowNewPassword(!showNewPassword)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-mid hover:text-primary transition-colors p-1.5 rounded-lg hover:bg-primary/5"
                        >
                          {showNewPassword ? (
                            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-5 h-5">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                            </svg>
                          ) : (
                            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-5 h-5">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            </svg>
                          )}
                        </button>
                      </div>
                      {errors.newPassword && (
                        <p className="mt-1.5 text-xs text-red-600">{errors.newPassword}</p>
                      )}
                    </div>

                    <div>
                      <label
                        htmlFor="confirmPassword"
                        className="block text-sm font-medium text-neutral-dark mb-2"
                      >
                        Confirm New Password
                      </label>
                      <div className="relative">
                        <input
                          type={showConfirmPassword ? 'text' : 'password'}
                          id="confirmPassword"
                          name="confirmPassword"
                          value={confirmPassword}
                          onChange={(e) => {
                            setConfirmPassword(e.target.value);
                            if (errors.confirmPassword) {
                              setErrors((prev) => {
                                const newErrors = { ...prev };
                                delete newErrors.confirmPassword;
                                return newErrors;
                              });
                            }
                          }}
                          className={`w-full px-4 py-3 rounded-xl border ${
                            errors.confirmPassword
                              ? 'border-red-300 focus:border-red-500 focus:ring-2 focus:ring-red-100'
                              : 'border-neutral-mid/20 focus:border-primary focus:ring-2 focus:ring-primary/10'
                          } focus:outline-none bg-white transition-all duration-200 text-neutral-dark placeholder:text-neutral-mid/50 pr-11`}
                          placeholder="Confirm new password"
                        />
                        <button
                          type="button"
                          onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-mid hover:text-primary transition-colors p-1.5 rounded-lg hover:bg-primary/5"
                        >
                          {showConfirmPassword ? (
                            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-5 h-5">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                            </svg>
                          ) : (
                            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-5 h-5">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            </svg>
                          )}
                        </button>
                      </div>
                      {errors.confirmPassword && (
                        <p className="mt-1.5 text-xs text-red-600">{errors.confirmPassword}</p>
                      )}
                    </div>

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
                          Resetting Password...
                        </span>
                      ) : (
                        'Reset Password'
                      )}
                    </button>
                  </form>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
