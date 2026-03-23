'use client';

import { useState, useEffect } from 'react';
import { getWhatsAppMessages } from '@/lib/whatsapp-api';

interface Props {
  credentialId: string;
  onClose: () => void;
}

export default function MessageHistoryModal({ credentialId, onClose }: Props) {
  const [messages, setMessages] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchMessages();
  }, []);

  const fetchMessages = async () => {
    setLoading(true);
    try {
      const data = await getWhatsAppMessages(credentialId, 50, 0);
      setMessages(data);
    } catch (err: any) {
      console.error('Failed to load messages:', err);
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'sent':
        return 'bg-blue-100 text-blue-700';
      case 'delivered':
        return 'bg-green-100 text-green-700';
      case 'read':
        return 'bg-purple-100 text-purple-700';
      case 'failed':
        return 'bg-red-100 text-red-700';
      default:
        return 'bg-gray-100 text-gray-700';
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-3xl rounded-3xl bg-white p-8 shadow-2xl max-h-[80vh] flex flex-col">
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-neutral-dark">Message History</h2>
          <p className="text-sm text-neutral-mid mt-2">Recent messages sent from this account</p>
        </div>

        <div className="flex-1 overflow-auto">
          {loading ? (
            <div className="text-center py-12">
              <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-primary border-r-transparent"></div>
              <p className="text-neutral-mid mt-4">Loading messages...</p>
            </div>
          ) : messages.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-neutral-mid">No messages sent yet</p>
            </div>
          ) : (
            <div className="space-y-3">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className="bg-gradient-to-br from-white to-green-50/30 border border-neutral-mid/10 rounded-xl p-4"
                >
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <p className="font-semibold text-neutral-dark">{message.to}</p>
                      <p className="text-xs text-neutral-mid">
                        {new Date(message.sent_at).toLocaleString()}
                      </p>
                    </div>
                    <span className={`px-3 py-1 rounded-full text-xs font-medium ${getStatusColor(message.status)}`}>
                      {message.status}
                    </span>
                  </div>
                  {message.error && (
                    <p className="text-sm text-red-600 mt-2">Error: {message.error}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="mt-6 pt-4 border-t border-neutral-mid/10">
          <button
            onClick={onClose}
            className="w-full px-5 py-3 rounded-xl border border-neutral-mid/20 text-neutral-dark font-semibold hover:bg-neutral-mid/5 transition-all duration-200"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
