'use client';

import { useState, useEffect, useRef, useCallback } from 'react';

interface DialPadProps {
  availableNumbers: { phone_number: string; provider: string; friendly_name?: string }[];
  onCall: (fromNumber: string, toNumber: string) => Promise<void>;
  isDarkMode: boolean;
  onClose: () => void;
  isVisible: boolean;
}

export function DialPad({ availableNumbers, onCall, isDarkMode, onClose, isVisible }: DialPadProps) {
  const [phoneNumber, setPhoneNumber] = useState('');
  const [selectedFrom, setSelectedFrom] = useState('');
  const [isCalling, setIsCalling] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleCall = useCallback(async () => {
    if (!selectedFrom || !phoneNumber) return;

    setIsCalling(true);
    try {
      await onCall(selectedFrom, phoneNumber);
      setPhoneNumber('');
    } catch (error) {
      console.error('Call failed:', error);
    } finally {
      setIsCalling(false);
    }
  }, [onCall, phoneNumber, selectedFrom]);

  // Handle keyboard numpad input
  useEffect(() => {
    if (!isVisible) return;

    const handleKeyPress = (e: KeyboardEvent) => {
      // Prevent default only for dial pad keys
      if (['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '*', '#', '+'].includes(e.key)) {
        e.preventDefault();
      }

      // Numpad and regular number keys
      if (e.key >= '0' && e.key <= '9') {
        setPhoneNumber(prev => prev + e.key);
      }
      // Backspace
      else if (e.key === 'Backspace') {
        e.preventDefault();
        setPhoneNumber(prev => prev.slice(0, -1));
      }
      // Enter to call
      else if (e.key === 'Enter' && phoneNumber && selectedFrom) {
        e.preventDefault();
        void handleCall();
      }
      // Special characters
      else if (e.key === '*' || e.key === '#' || e.key === '+') {
        setPhoneNumber(prev => prev + e.key);
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [handleCall, isVisible, phoneNumber, selectedFrom]);

  // Focus input when visible
  useEffect(() => {
    if (isVisible && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isVisible]);

  const handleDigit = (digit: string) => {
    setPhoneNumber(prev => prev + digit);
  };

  const handleBackspace = () => {
    setPhoneNumber(prev => prev.slice(0, -1));
  };

  const digits = [
    { digit: '1', letters: '' },
    { digit: '2', letters: 'ABC' },
    { digit: '3', letters: 'DEF' },
    { digit: '4', letters: 'GHI' },
    { digit: '5', letters: 'JKL' },
    { digit: '6', letters: 'MNO' },
    { digit: '7', letters: 'PQRS' },
    { digit: '8', letters: 'TUV' },
    { digit: '9', letters: 'WXYZ' },
    { digit: '*', letters: '' },
    { digit: '0', letters: '+' },
    { digit: '#', letters: '' },
  ];

  return (
    <div className={`${isDarkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} rounded-2xl p-8 max-w-md w-full border shadow-2xl relative`}>
      {/* Close Button */}
      <button
        onClick={onClose}
        className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center rounded-full bg-red-500 hover:bg-red-600 text-white font-bold transition-colors"
      >
        ×
      </button>

      <h2 className={`text-2xl font-bold mb-6 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
        📞 Dial Pad
      </h2>

      {/* From Number Selector */}
      <div className="mb-6">
        <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
          Call From:
        </label>
        <select
          value={selectedFrom}
          onChange={(e) => setSelectedFrom(e.target.value)}
          className={`w-full px-4 py-3 rounded-lg border ${
            isDarkMode
              ? 'bg-gray-700 border-gray-600 text-white'
              : 'bg-gray-50 border-gray-300 text-gray-900'
          } focus:outline-none focus:ring-2 focus:ring-primary`}
        >
          <option value="">Select your number...</option>
          {availableNumbers.map((num) => (
            <option key={num.phone_number} value={num.phone_number}>
              {num.friendly_name || num.phone_number} ({num.provider.toUpperCase()})
            </option>
          ))}
        </select>
      </div>

      {/* Display Screen */}
      <div className={`${
        isDarkMode ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-900'
      } rounded-xl p-4 mb-6 text-center text-3xl font-mono h-20 flex items-center justify-center tracking-wider`}>
        {phoneNumber || <span className="text-gray-400">+</span>}
      </div>

      {/* Dial Pad Grid */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {digits.map(({ digit, letters }) => (
          <button
            key={digit}
            onClick={() => handleDigit(digit)}
            disabled={isCalling}
            className={`${
              isDarkMode
                ? 'bg-gray-700 hover:bg-gray-600 text-white'
                : 'bg-gray-100 hover:bg-gray-200 text-gray-900'
            } rounded-xl h-16 flex flex-col items-center justify-center transition-all duration-150 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            <span className="text-2xl font-semibold">{digit}</span>
            {letters && (
              <span className={`text-xs ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                {letters}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Action Buttons */}
      <div className="flex gap-3">
        <button
          onClick={handleBackspace}
          disabled={!phoneNumber || isCalling}
          className={`flex-1 py-4 rounded-xl font-semibold transition-all duration-150 ${
            isDarkMode
              ? 'bg-gray-700 hover:bg-gray-600 text-white'
              : 'bg-gray-100 hover:bg-gray-200 text-gray-900'
          } disabled:opacity-50 disabled:cursor-not-allowed active:scale-95`}
        >
          ← Delete
        </button>
        <button
          onClick={handleCall}
          disabled={!selectedFrom || !phoneNumber || isCalling}
          className="flex-1 py-4 rounded-xl font-semibold bg-green-500 hover:bg-green-600 text-white disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-150 active:scale-95 flex items-center justify-center gap-2"
        >
          {isCalling ? (
            <>
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
              Calling...
            </>
          ) : (
            <>
              📞 Call
            </>
          )}
        </button>
      </div>

      {/* Helper Text */}
      {!selectedFrom && (
        <p className={`mt-4 text-sm text-center ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
          Please select a number to call from
        </p>
      )}
    </div>
  );
}
