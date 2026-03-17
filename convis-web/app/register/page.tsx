'use client';

import { useState } from 'react';
import Link from 'next/link';
import { DotLottieReact } from '@lottiefiles/dotlottie-react';

export default function RegisterPage() {
  const [formData, setFormData] = useState({
    companyName: '',
    email: '',
    password: '',
    confirmPassword: '',
    phoneNumber: '',
  });

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    if (!formData.companyName.trim()) {
      newErrors.companyName = 'Company name is required';
    }

    if (!formData.email.trim()) {
      newErrors.email = 'Email is required';
    } else if (!/\S+@\S+\.\S+/.test(formData.email)) {
      newErrors.email = 'Email is invalid';
    }

    if (!formData.password) {
      newErrors.password = 'Password is required';
    } else if (formData.password.length < 6) {
      newErrors.password = 'Password must be at least 6 characters';
    }

    if (!formData.confirmPassword) {
      newErrors.confirmPassword = 'Please confirm your password';
    } else if (formData.password !== formData.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
    }

    if (!formData.phoneNumber.trim()) {
      newErrors.phoneNumber = 'Phone number is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSuccessMessage('');

    if (!validateForm()) {
      return;
    }

    setIsLoading(true);

    try {
      const { registerUser } = await import('@/lib/api');
      const data = await registerUser({
        companyName: formData.companyName,
        email: formData.email,
        password: formData.password,
        phoneNumber: formData.phoneNumber,
      });

      setSuccessMessage(data.message);

      // Redirect to OTP verification page after 2 seconds
      setTimeout(() => {
        window.location.href = `/verify-email?email=${encodeURIComponent(formData.email)}`;
      }, 2000);
    } catch (error) {
      if (error instanceof Error) {
        setErrors({ submit: error.message });
      } else {
        setErrors({ submit: 'Network error. Please try again.' });
      }
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
                Welcome to Convis AI
              </h1>
              <p className="text-white/80 text-sm">
                Create your account to get started
              </p>
            </div>

            {/* Left Side - Blue Section */}
            <div className="relative bg-gradient-to-br from-primary via-primary to-primary/90 p-8 lg:p-12 flex flex-col justify-between overflow-hidden hidden lg:flex">
              {/* Decorative Wave/Cloud Pattern - Diagonal waves */}
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
                  Welcome to<br />Convis AI
                </h1>

                <p className="text-white/90 text-base lg:text-lg leading-relaxed max-w-md mb-8">
                  Transform customer interactions with AI-powered voice assistants.
                  Automate calls, boost efficiency, and deliver exceptional experiences 24/7.
                </p>

                {/* Feature highlights */}
                <div className="space-y-3 text-white/80 text-sm">
                  <div className="flex items-center gap-3">
                    <svg className="w-5 h-5 text-accent" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>Intelligent voice conversations</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <svg className="w-5 h-5 text-accent" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>24/7 automated support</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <svg className="w-5 h-5 text-accent" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>Enterprise-grade security</span>
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
                    Create your account
                  </h2>
                  <p className="text-neutral-mid text-sm">
                    Join thousands of businesses using Convis AI
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
            {/* Company Name */}
            <div>
              <label
                htmlFor="companyName"
                className="block text-sm font-medium text-neutral-dark mb-2"
              >
                Company Name
              </label>
              <input
                type="text"
                id="companyName"
                name="companyName"
                value={formData.companyName}
                onChange={handleChange}
                className={`w-full px-4 py-3 rounded-xl border ${
                  errors.companyName
                    ? 'border-red-300 focus:border-red-500 focus:ring-2 focus:ring-red-100'
                    : 'border-neutral-mid/20 focus:border-primary focus:ring-2 focus:ring-primary/10'
                } focus:outline-none bg-white transition-all duration-200 text-neutral-dark placeholder:text-neutral-mid/50`}
                placeholder="Acme Corporation"
              />
              {errors.companyName && (
                <p className="mt-1.5 text-xs text-red-600">{errors.companyName}</p>
              )}
            </div>

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
              <label
                htmlFor="password"
                className="block text-sm font-medium text-neutral-dark mb-2"
              >
                Password
              </label>
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

            {/* Confirm Password */}
            <div>
              <label
                htmlFor="confirmPassword"
                className="block text-sm font-medium text-neutral-dark mb-2"
              >
                Confirm Password
              </label>
              <div className="relative">
                <input
                  type={showConfirmPassword ? 'text' : 'password'}
                  id="confirmPassword"
                  name="confirmPassword"
                  value={formData.confirmPassword}
                  onChange={handleChange}
                  className={`w-full px-4 py-3 rounded-xl border ${
                    errors.confirmPassword
                      ? 'border-red-300 focus:border-red-500 focus:ring-2 focus:ring-red-100'
                      : 'border-neutral-mid/20 focus:border-primary focus:ring-2 focus:ring-primary/10'
                  } focus:outline-none bg-white transition-all duration-200 text-neutral-dark placeholder:text-neutral-mid/50 pr-11`}
                  placeholder="Confirm your password"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-mid hover:text-primary transition-colors p-1.5 rounded-lg hover:bg-primary/5"
                  aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
                >
                  {showConfirmPassword ? (
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
              {errors.confirmPassword && (
                <p className="mt-1.5 text-xs text-red-600">{errors.confirmPassword}</p>
              )}
            </div>

            {/* Phone Number */}
            <div>
              <label
                htmlFor="phoneNumber"
                className="block text-sm font-medium text-neutral-dark mb-2"
              >
                Phone Number
              </label>
              <input
                type="tel"
                id="phoneNumber"
                name="phoneNumber"
                value={formData.phoneNumber}
                onChange={handleChange}
                className={`w-full px-4 py-3 rounded-xl border ${
                  errors.phoneNumber
                    ? 'border-red-300 focus:border-red-500 focus:ring-2 focus:ring-red-100'
                    : 'border-neutral-mid/20 focus:border-primary focus:ring-2 focus:ring-primary/10'
                } focus:outline-none bg-white transition-all duration-200 text-neutral-dark placeholder:text-neutral-mid/50`}
                placeholder="+1 (555) 000-0000"
              />
              {errors.phoneNumber && (
                <p className="mt-1.5 text-xs text-red-600">{errors.phoneNumber}</p>
              )}
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
                  Creating Account...
                </span>
              ) : (
                'Sign Up'
              )}
            </button>

            {/* Sign In Link */}
            <p className="text-center text-sm text-neutral-mid mt-6">
              Already a member?{' '}
              <Link
                href="/login"
                className="text-primary font-semibold hover:text-primary/80 transition-colors"
              >
                Login
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
