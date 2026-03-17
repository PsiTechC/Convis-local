// API Configuration
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai';

// Safe JSON parse utility - prevents crashes from corrupted localStorage
export function safeJsonParse<T>(jsonString: string | null, defaultValue: T): T {
  if (!jsonString) return defaultValue;
  try {
    return JSON.parse(jsonString) as T;
  } catch {
    console.warn('Failed to parse JSON:', jsonString?.substring(0, 100));
    return defaultValue;
  }
}

// Safe response.json() parser with error handling
export async function safeResponseJson<T>(response: Response, defaultValue: T): Promise<T> {
  try {
    return await response.json() as T;
  } catch {
    return defaultValue;
  }
}

// Phone number validation utility
export const PHONE_REGEX = /^\+?[1-9]\d{1,14}$/;

export function validatePhoneNumber(phone: string): { isValid: boolean; cleanedNumber: string } {
  const cleanedNumber = phone.replace(/[\s\-()]/g, '');
  const isValid = PHONE_REGEX.test(cleanedNumber);
  return { isValid, cleanedNumber };
}

// Token validation utility
export function getValidToken(): string | null {
  if (typeof window === 'undefined') return null;
  const token = localStorage.getItem('token');
  if (!token || token === 'undefined' || token === 'null') {
    return null;
  }
  return token;
}

// Get current user from localStorage safely
export interface StoredUser {
  id?: string;
  _id?: string;
  clientId?: string;
  email?: string;
  companyName?: string;
  name?: string;
  first_name?: string;
  last_name?: string;
  phone?: string;
  isAdmin?: boolean;
}

export function getStoredUser(): StoredUser | null {
  const userStr = localStorage.getItem('user');
  return safeJsonParse<StoredUser | null>(userStr, null);
}

export function getUserId(user: StoredUser | null): string | null {
  if (!user) return null;
  return user.clientId || user._id || user.id || null;
}
export interface RegisterData {
  companyName: string;
  email: string;
  password: string;
  phoneNumber: string;
}

export interface RegisterResponse {
  message: string;
  userId?: string;
}

export interface VerifyEmailData {
  email: string;
  otp: string;
}

export interface VerifyEmailResponse {
  message: string;
}

export interface ApiError {
  detail: string;
}

export async function registerUser(data: RegisterData): Promise<RegisterResponse> {
  const response = await fetch(`${API_BASE_URL}/api/register/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  const result = await response.json();

  if (!response.ok) {
    // Handle Pydantic validation errors (FastAPI returns them as an array)
    if (result.detail && Array.isArray(result.detail)) {
      const errorMessages = result.detail.map((err: { loc?: string[]; msg?: string }) => {
        const field = err.loc?.[err.loc.length - 1] || 'field';
        return `${field}: ${err.msg}`;
      }).join(', ');
      throw new Error(errorMessages || 'Validation failed');
    }
    throw new Error(result.detail || 'Registration failed');
  }

  return result;
}

export async function verifyEmail(data: VerifyEmailData): Promise<VerifyEmailResponse> {
  const response = await fetch(`${API_BASE_URL}/api/register/verify-email`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  const result = await response.json();

  if (!response.ok) {
    throw new Error(result.detail || 'Verification failed');
  }

  return result;
}

export interface LoginData {
  email: string;
  password: string;
}

export interface LoginResponse {
  redirectUrl: string;
  clientId: string;
  isAdmin_683ed29d13d9992915a2a803_amdin_: boolean;
  token: string;
}

export async function loginUser(data: LoginData): Promise<LoginResponse> {
  const response = await fetch(`${API_BASE_URL}/api/access/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  const result = await response.json();

  if (!response.ok) {
    throw new Error(result.detail || 'Login failed');
  }

  return result;
}
