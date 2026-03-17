'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { DotLottieReact } from '@lottiefiles/dotlottie-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai';




export default function LoginPage() {
  const router = useRouter();
  const [formData, setFormData] = useState({
    email: '',
    password: '',
  });

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    if (!formData.email.trim()) {
      newErrors.email = 'Email is required';
    } else if (!/\S+@\S+\.\S+/.test(formData.email)) {
      newErrors.email = 'Email is invalid';
    }

    if (!formData.password) {
      newErrors.password = 'Password is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setIsLoading(true);

    try {
      const response = await fetch(`${API_URL}/api/access/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: formData.email,
          password: formData.password,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        // Store token
        if (data.token) {
          localStorage.setItem('token', data.token);
        }

        // Store clientId if provided
        if (data.clientId) {
          localStorage.setItem('clientId', data.clientId);
        }

        // Store isAdmin flag
        if (data.isAdmin_683ed29d13d9992915a2a803_amdin_ !== undefined) {
          localStorage.setItem('isAdmin', data.isAdmin_683ed29d13d9992915a2a803_amdin_.toString());
        }

        // Store redirectUrl
        if (data.redirectUrl) {
          localStorage.setItem('redirectUrl', data.redirectUrl);
        }

        // Get user email from form data for display
        const userInfo = {
          email: formData.email,
          id: data.clientId, // Store clientId as id for compatibility
          _id: data.clientId, // Also store as _id for MongoDB compatibility
          clientId: data.clientId,
          isAdmin: data.isAdmin_683ed29d13d9992915a2a803_amdin_ || false,
        };
        localStorage.setItem('user', JSON.stringify(userInfo));

        // Always redirect to our dashboard page
        router.push('/dashboard');
      } else {
        setErrors({ submit: data.detail || 'Login failed. Please check your credentials.' });
      }
    } catch (_error) {
      setErrors({ submit: 'Network error. Please try again.' });
    } finally {
      setIsLoading(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    // Clear error for this field when user starts typing
    if (errors[name]) {
      setErrors((prev) => {
        const newErrors = { ...prev };
        delete newErrors[name];
        return newErrors;
      });
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-neutral-mid/5 to-neutral-light p-4 lg:p-8">
      <div className="w-full max-w-6xl">
        {/* Main Card */}
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
                Welcome Back!
              </h1>
              <p className="text-white/80 text-sm">
                Sign in to continue to Convis AI
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
                {/* Logo/Icon - AI Assistant themed */}
                <div className="w-20 h-20 bg-white rounded-2xl flex items-center justify-center mb-8 shadow-2xl">
                  <DotLottieReact
                    src="/microphone-animation.lottie"
                    loop
                    autoplay
                    style={{ width: '48px', height: '48px' }}
                  />
                </div>

                <h1 className="text-4xl lg:text-5xl font-bold text-white mb-4 font-heading leading-tight">
                  Welcome Back!
                </h1>

                <p className="text-white/90 text-base lg:text-lg leading-relaxed max-w-md mb-8">
                  Sign in to access your AI voice assistant dashboard and manage your automated conversations.
                </p>

                {/* Feature highlights */}
                <div className="space-y-3 text-white/80 text-sm">
                  <div className="flex items-center gap-3">
                    <svg className="w-5 h-5 text-accent" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>Access your AI assistants</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <svg className="w-5 h-5 text-accent" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>View call analytics & insights</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <svg className="w-5 h-5 text-accent" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>Manage your account settings</span>
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
                    Sign in to your account
                  </h2>
                  <p className="text-neutral-mid text-sm">
                    Enter your credentials to access your dashboard
                  </p>
                </div>

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

                <form onSubmit={handleSubmit} className="space-y-5">
                  {/* Email */}
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
                      value={formData.email}
                      onChange={handleChange}
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

                  {/* Password */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <label
                        htmlFor="password"
                        className="block text-sm font-medium text-neutral-dark"
                      >
                        Password
                      </label>
                      <Link
                        href="/forgot-password"
                        className="text-xs text-primary hover:text-primary/80 transition-colors font-medium"
                      >
                        Forgot password?
                      </Link>
                    </div>
                    <div className="relative">
                      <input
                        type={showPassword ? 'text' : 'password'}
                        id="password"
                        name="password"
                        value={formData.password}
                        onChange={handleChange}
                        className={`w-full px-4 py-3 rounded-xl border ${
                          errors.password
                            ? 'border-red-300 focus:border-red-500 focus:ring-2 focus:ring-red-100'
                            : 'border-neutral-mid/20 focus:border-primary focus:ring-2 focus:ring-primary/10'
                        } focus:outline-none bg-white transition-all duration-200 text-neutral-dark placeholder:text-neutral-mid/50 pr-11`}
                        placeholder="Enter your password"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-mid hover:text-primary transition-colors p-1.5 rounded-lg hover:bg-primary/5"
                        aria-label={showPassword ? 'Hide password' : 'Show password'}
                      >
                        {showPassword ? (
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            fill="none"
                            viewBox="0 0 24 24"
                            strokeWidth={2}
                            stroke="currentColor"
                            className="w-5 h-5"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88"
                            />
                          </svg>
                        ) : (
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            fill="none"
                            viewBox="0 0 24 24"
                            strokeWidth={2}
                            stroke="currentColor"
                            className="w-5 h-5"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z"
                            />
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                            />
                          </svg>
                        )}
                      </button>
                    </div>
                    {errors.password && (
                      <p className="mt-1.5 text-xs text-red-600">{errors.password}</p>
                    )}
                  </div>

                  {/* Remember Me */}
                  <div className="flex items-center">
                    <input
                      id="remember-me"
                      name="remember-me"
                      type="checkbox"
                      checked={rememberMe}
                      onChange={(e) => setRememberMe(e.target.checked)}
                      className="h-4 w-4 rounded border-neutral-mid/30 text-primary focus:ring-2 focus:ring-primary focus:ring-offset-0 cursor-pointer"
                    />
                    <label
                      htmlFor="remember-me"
                      className="ml-2 block text-sm text-neutral-mid cursor-pointer select-none"
                    >
                      Remember me
                    </label>
                  </div>

                  {/* Submit Button */}
                  <button
                    type="submit"
                    disabled={isLoading}
                    className="w-full bg-gradient-to-r from-primary via-primary to-primary/90 text-white py-3.5 px-6 rounded-xl font-semibold hover:shadow-xl hover:shadow-primary/20 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 shadow-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none mt-2"
                  >
                    {isLoading ? (
                      <span className="flex items-center justify-center gap-2">
                        <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Signing in...
                      </span>
                    ) : (
                      'Sign In'
                    )}
                  </button>

                  {/* Sign Up Link */}
                  <p className="text-center text-sm text-neutral-mid mt-6">
                    Don&apos;t have an account?{' '}
                    <Link
                      href="/register"
                      className="text-primary font-semibold hover:text-primary/80 transition-colors"
                    >
                      Sign Up
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
