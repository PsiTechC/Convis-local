'use client';

import { useState } from 'react';
import { testWhatsAppConnection, createWhatsAppCredential } from '@/lib/whatsapp-api';

interface Props {
  onClose: () => void;
  onSuccess: () => void;
}

export default function AddCredentialModal({ onClose, onSuccess }: Props) {
  const [formData, setFormData] = useState({
    label: '',
    api_key: '',
    bearer_token: '',
    api_url: 'https://whatsapp-api-backend-production.up.railway.app',
  });
  const [errors, setErrors] = useState<any>({});
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    setErrors((prev: any) => ({ ...prev, [name]: '' }));
  };

  const handleTestConnection = async () => {
    if (!formData.api_key || !formData.bearer_token) {
      alert('Please enter API Key and Bearer Token first');
      return;
    }

    setTesting(true);
    setTestResult(null);

    try {
      const result = await testWhatsAppConnection(
        formData.api_key,
        formData.bearer_token,
        formData.api_url
      );
      setTestResult(result);

      if (result.success) {
        alert(`✅ Connection successful!\n\nTemplates Found: ${result.templates_count || 0}\nAPI Status: ${result.api_accessible ? 'Accessible' : 'Not accessible'}`);
      } else {
        alert(`❌ ${result.message}`);
      }
    } catch (err: any) {
      alert(`Connection test failed: ${err.message}`);
    } finally {
      setTesting(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const newErrors: any = {};
    if (!formData.label.trim()) newErrors.label = 'Label is required';
    if (!formData.api_key.trim()) newErrors.api_key = 'API Key is required';
    if (!formData.bearer_token.trim()) newErrors.bearer_token = 'Bearer Token is required';

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    setLoading(true);

    try {
      await createWhatsAppCredential(formData);
      onSuccess();
      onClose();
    } catch (err: any) {
      alert(`Failed to save credentials: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-2xl rounded-3xl bg-white p-8 shadow-2xl">
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-neutral-dark">Add Railway WhatsApp API</h2>
          <p className="text-sm text-neutral-mid mt-2">
            Connect your Railway WhatsApp API credentials
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Label */}
          <div>
            <label className="block text-sm font-medium text-neutral-dark mb-2">
              Label <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              name="label"
              value={formData.label}
              onChange={handleChange}
              placeholder="e.g., My Business WhatsApp"
              className={`w-full px-4 py-3 rounded-xl border ${
                errors.label
                  ? 'border-red-300 focus:border-red-500'
                  : 'border-neutral-mid/20 focus:border-primary'
              } focus:outline-none focus:ring-2 focus:ring-primary/10`}
            />
            {errors.label && <p className="mt-1.5 text-xs text-red-600">{errors.label}</p>}
          </div>

          {/* API Key */}
          <div>
            <label className="block text-sm font-medium text-neutral-dark mb-2">
              API Key (x-api-key) <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              name="api_key"
              value={formData.api_key}
              onChange={handleChange}
              placeholder="ef99d3d2-e032-4c04-8e27-9313b2e6b172"
              className={`w-full px-4 py-3 rounded-xl border ${
                errors.api_key
                  ? 'border-red-300 focus:border-red-500'
                  : 'border-neutral-mid/20 focus:border-primary'
              } focus:outline-none focus:ring-2 focus:ring-primary/10`}
            />
            {errors.api_key && <p className="mt-1.5 text-xs text-red-600">{errors.api_key}</p>}
          </div>

          {/* Bearer Token */}
          <div>
            <label className="block text-sm font-medium text-neutral-dark mb-2">
              Bearer Token <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              name="bearer_token"
              value={formData.bearer_token}
              onChange={handleChange}
              placeholder="bn-9a32959187ad4140bf0b2c48b7c9cb08"
              className={`w-full px-4 py-3 rounded-xl border ${
                errors.bearer_token
                  ? 'border-red-300 focus:border-red-500'
                  : 'border-neutral-mid/20 focus:border-primary'
              } focus:outline-none focus:ring-2 focus:ring-primary/10`}
            />
            {errors.bearer_token && <p className="mt-1.5 text-xs text-red-600">{errors.bearer_token}</p>}
          </div>

          {/* API URL (Optional) */}
          <div>
            <label className="block text-sm font-medium text-neutral-dark mb-2">
              API URL (Optional)
            </label>
            <input
              type="text"
              name="api_url"
              value={formData.api_url}
              onChange={handleChange}
              placeholder="https://whatsapp-api-backend-production.up.railway.app"
              className="w-full px-4 py-3 rounded-xl border border-neutral-mid/20 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/10"
            />
            <p className="mt-1.5 text-xs text-neutral-mid">Leave default unless using custom deployment</p>
          </div>

          {/* Action Buttons */}
          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={handleTestConnection}
              disabled={testing}
              className="flex-1 px-5 py-3 rounded-xl border border-primary text-primary font-semibold hover:bg-primary/5 disabled:opacity-50 transition-all duration-200"
            >
              {testing ? 'Testing...' : 'Test Connection'}
            </button>
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="px-5 py-3 rounded-xl border border-neutral-mid/20 text-neutral-dark font-semibold hover:bg-neutral-mid/5 disabled:opacity-50 transition-all duration-200"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !testResult?.success}
              className="px-5 py-3 rounded-xl bg-gradient-to-r from-green-500 to-green-600 text-white font-semibold shadow-lg hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
            >
              {loading ? 'Saving...' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
