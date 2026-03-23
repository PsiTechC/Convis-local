'use client';

import { useState } from 'react';
import { createWhatsAppTemplate } from '@/lib/whatsapp-api';

interface Props {
  credentialId: string;
  onClose: () => void;
  onSuccess: () => void;
}

export default function CreateTemplateModal({ credentialId, onClose, onSuccess }: Props) {
  const [templateName, setTemplateName] = useState('');
  const [category, setCategory] = useState<'UTILITY' | 'MARKETING' | 'AUTHENTICATION'>('UTILITY');
  const [language, setLanguage] = useState('en');
  const [bodyText, setBodyText] = useState('');
  const [headerText, setHeaderText] = useState('');
  const [footerText, setFooterText] = useState('');
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<any>({});

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const newErrors: any = {};
    if (!templateName.trim()) newErrors.templateName = 'Template name is required';
    if (!/^[a-z0-9_]+$/.test(templateName)) {
      newErrors.templateName = 'Use only lowercase letters, numbers, and underscores';
    }
    if (!bodyText.trim()) newErrors.bodyText = 'Message body is required';

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    setLoading(true);

    try {
      const response = await createWhatsAppTemplate({
        credential_id: credentialId,
        template_name: templateName.toLowerCase().replace(/\s+/g, '_'),
        category,
        language,
        body_text: bodyText,
        header_text: headerText || undefined,
        footer_text: footerText || undefined,
      });

      alert(`✅ ${response.message}`);
      onSuccess();
      onClose();
    } catch (err: any) {
      alert(`Failed to create template: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-2xl rounded-3xl bg-white p-8 shadow-2xl max-h-[90vh] overflow-y-auto">
        <h2 className="text-2xl font-bold text-neutral-dark mb-6">Create WhatsApp Template</h2>
        <p className="text-sm text-neutral-mid mb-6">
          Create a new message template. Templates must be approved by WhatsApp before use (usually takes a few minutes).
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-neutral-dark mb-2">
              Template Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={templateName}
              onChange={(e) => {
                setTemplateName(e.target.value);
                setErrors((prev: any) => ({ ...prev, templateName: '' }));
              }}
              placeholder="my_template_name"
              className={`w-full px-4 py-3 rounded-xl border ${
                errors.templateName
                  ? 'border-red-300 focus:border-red-500'
                  : 'border-neutral-mid/20 focus:border-primary'
              } focus:outline-none focus:ring-2 focus:ring-primary/10`}
            />
            {errors.templateName && <p className="mt-1.5 text-xs text-red-600">{errors.templateName}</p>}
            <p className="mt-1.5 text-xs text-neutral-mid">Use only lowercase letters, numbers, and underscores</p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-neutral-dark mb-2">
                Category <span className="text-red-500">*</span>
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value as any)}
                className="w-full px-4 py-3 rounded-xl border border-neutral-mid/20 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/10"
              >
                <option value="UTILITY">Utility</option>
                <option value="MARKETING">Marketing</option>
                <option value="AUTHENTICATION">Authentication</option>
              </select>
              <p className="mt-1.5 text-xs text-neutral-mid">Template purpose</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-neutral-dark mb-2">
                Language <span className="text-red-500">*</span>
              </label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className="w-full px-4 py-3 rounded-xl border border-neutral-mid/20 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/10"
              >
                <option value="en">English</option>
                <option value="en_US">English (US)</option>
                <option value="en_GB">English (UK)</option>
                <option value="hi">Hindi</option>
                <option value="es">Spanish</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-neutral-dark mb-2">
              Header Text (Optional)
            </label>
            <input
              type="text"
              value={headerText}
              onChange={(e) => setHeaderText(e.target.value)}
              placeholder="Welcome Message"
              className="w-full px-4 py-3 rounded-xl border border-neutral-mid/20 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/10"
            />
            <p className="mt-1.5 text-xs text-neutral-mid">Optional header displayed above the message</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-neutral-dark mb-2">
              Message Body <span className="text-red-500">*</span>
            </label>
            <textarea
              value={bodyText}
              onChange={(e) => {
                setBodyText(e.target.value);
                setErrors((prev: any) => ({ ...prev, bodyText: '' }));
              }}
              placeholder="Hello {{1}}, your order {{2}} is ready for pickup."
              rows={6}
              className={`w-full px-4 py-3 rounded-xl border ${
                errors.bodyText
                  ? 'border-red-300 focus:border-red-500'
                  : 'border-neutral-mid/20 focus:border-primary'
              } focus:outline-none focus:ring-2 focus:ring-primary/10`}
            />
            {errors.bodyText && <p className="mt-1.5 text-xs text-red-600">{errors.bodyText}</p>}
            <p className="mt-1.5 text-xs text-neutral-mid">
              Use {'{'}{'{'} 1 {'}'}{'}'},  {'{'}{'{'} 2 {'}'}{'}'},  etc. for dynamic values. Example: Hello {'{'}{'{'} 1 {'}'}{'}'}, your appointment is on {'{'}{'{'} 2 {'}'}{'}'}.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-neutral-dark mb-2">
              Footer Text (Optional)
            </label>
            <input
              type="text"
              value={footerText}
              onChange={(e) => setFooterText(e.target.value)}
              placeholder="Reply STOP to unsubscribe"
              className="w-full px-4 py-3 rounded-xl border border-neutral-mid/20 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/10"
            />
            <p className="mt-1.5 text-xs text-neutral-mid">Optional footer displayed below the message</p>
          </div>

          <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mt-4">
            <p className="text-sm text-blue-800">
              <strong>Note:</strong> After creating, your template will be submitted to WhatsApp for approval.
              This usually takes a few minutes. You&apos;ll be able to use it once it&apos;s approved.
            </p>
          </div>

          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="flex-1 px-5 py-3 rounded-xl border border-neutral-mid/20 text-neutral-dark font-semibold hover:bg-neutral-mid/5 disabled:opacity-50 transition-all duration-200"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 px-5 py-3 rounded-xl bg-gradient-to-r from-primary to-purple-600 text-white font-semibold shadow-lg hover:shadow-xl disabled:opacity-50 transition-all duration-200"
            >
              {loading ? 'Creating...' : 'Create Template'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
