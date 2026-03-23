/**
 * WhatsApp API Client
 * Functions for interacting with WhatsApp integration endpoints
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.convis.ai';

/**
 * Get authentication token from localStorage
 */
function getAuthToken(): string {
  if (typeof window === 'undefined') return '';
  return localStorage.getItem('token') || '';
}

/**
 * Make authenticated API request
 */
async function apiRequest(endpoint: string, options: RequestInit = {}) {
  const token = getAuthToken();

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Request failed' }));
    throw new Error(error.detail || error.message || 'Request failed');
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return null;
  }

  return response.json();
}

// ============= Credentials =============

export interface WhatsAppCredentialCreate {
  label: string;
  api_key: string;
  bearer_token: string;
  api_url?: string;
}

export interface WhatsAppCredential {
  id: string;
  user_id: string;
  label: string;
  last_four: string;
  api_url_masked: string;
  status: 'active' | 'disconnected' | 'error';
  created_at: string;
  updated_at?: string;
}

export interface WhatsAppConnectionTestResult {
  success: boolean;
  message: string;
  templates_count?: number;
  api_accessible?: boolean;
}

/**
 * Test Railway WhatsApp API connection before saving credentials
 */
export async function testWhatsAppConnection(
  api_key: string,
  bearer_token: string,
  api_url?: string
): Promise<WhatsAppConnectionTestResult> {
  return apiRequest('/api/whatsapp/test-connection', {
    method: 'POST',
    body: JSON.stringify({ api_key, bearer_token, api_url }),
  });
}

/**
 * Create new WhatsApp credential
 */
export async function createWhatsAppCredential(
  data: WhatsAppCredentialCreate
): Promise<WhatsAppCredential> {
  return apiRequest('/api/whatsapp/credentials', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Get all WhatsApp credentials for current user
 */
export async function getWhatsAppCredentials(): Promise<WhatsAppCredential[]> {
  return apiRequest('/api/whatsapp/credentials');
}

/**
 * Get a specific WhatsApp credential
 */
export async function getWhatsAppCredential(credentialId: string): Promise<WhatsAppCredential> {
  return apiRequest(`/api/whatsapp/credentials/${credentialId}`);
}

/**
 * Update WhatsApp credential
 */
export async function updateWhatsAppCredential(
  credentialId: string,
  data: Partial<WhatsAppCredentialCreate>
): Promise<WhatsAppCredential> {
  return apiRequest(`/api/whatsapp/credentials/${credentialId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

/**
 * Delete WhatsApp credential
 */
export async function deleteWhatsAppCredential(credentialId: string): Promise<void> {
  return apiRequest(`/api/whatsapp/credentials/${credentialId}`, {
    method: 'DELETE',
  });
}

/**
 * Verify WhatsApp credential connection
 */
export async function verifyWhatsAppCredential(
  credentialId: string
): Promise<WhatsAppConnectionTestResult> {
  return apiRequest(`/api/whatsapp/credentials/${credentialId}/verify`, {
    method: 'POST',
  });
}

// ============= Messages =============

export interface WhatsAppMessageSend {
  credential_id: string;
  to: string;
  message_type: 'text' | 'template';
  text?: string;
  template_name?: string;
  template_params?: string[];
}

export interface WhatsAppMessageBulkSend {
  credential_id: string;
  recipients: string[];
  message_type: 'text' | 'template';
  text?: string;
  template_name?: string;
  template_params?: string[];
}

export interface WhatsAppMessage {
  id: string;
  message_id?: string;
  to: string;
  status: 'queued' | 'sent' | 'delivered' | 'read' | 'failed';
  message_type: string;
  sent_at: string;
  error?: string;
}

export interface WhatsAppTemplate {
  id: string;
  name: string;
  status: string;
  category: string;
  language: string;
  components: any[];
}

/**
 * Send a WhatsApp message
 */
export async function sendWhatsAppMessage(
  data: WhatsAppMessageSend
): Promise<WhatsAppMessage> {
  return apiRequest('/api/whatsapp/send', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Send bulk WhatsApp messages
 */
export async function sendBulkWhatsAppMessages(
  data: WhatsAppMessageBulkSend
): Promise<{ success: boolean; message: string; recipients_count: number }> {
  return apiRequest('/api/whatsapp/send-bulk', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Get WhatsApp message history
 */
export async function getWhatsAppMessages(
  credentialId?: string,
  limit: number = 50,
  offset: number = 0
): Promise<WhatsAppMessage[]> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });

  if (credentialId) {
    params.append('credential_id', credentialId);
  }

  return apiRequest(`/api/whatsapp/messages?${params}`);
}

/**
 * Delete a message from history
 */
export async function deleteWhatsAppMessage(messageId: string): Promise<void> {
  return apiRequest(`/api/whatsapp/messages/${messageId}`, {
    method: 'DELETE',
  });
}

/**
 * Get WhatsApp templates for a credential
 */
export async function getWhatsAppTemplates(credentialId: string): Promise<WhatsAppTemplate[]> {
  return apiRequest(`/api/whatsapp/templates?credential_id=${credentialId}`);
}

export interface WhatsAppTemplateCreate {
  credential_id: string;
  template_name: string;
  category: 'UTILITY' | 'MARKETING' | 'AUTHENTICATION';
  language: string;
  body_text: string;
  header_text?: string;
  footer_text?: string;
}

/**
 * Create a new WhatsApp template
 */
export async function createWhatsAppTemplate(
  data: WhatsAppTemplateCreate
): Promise<{ success: boolean; message: string; template: any }> {
  const params = new URLSearchParams({
    credential_id: data.credential_id,
    template_name: data.template_name,
    category: data.category,
    language: data.language,
    body_text: data.body_text,
  });

  if (data.header_text) {
    params.append('header_text', data.header_text);
  }

  if (data.footer_text) {
    params.append('footer_text', data.footer_text);
  }

  return apiRequest(`/api/whatsapp/templates/create?${params}`, {
    method: 'POST',
  });
}

// ============= Stats =============

export interface WhatsAppStats {
  total_messages: number;
  sent: number;
  delivered: number;
  read: number;
  failed: number;
  credentials_count: number;
  active_credentials: number;
}

/**
 * Get WhatsApp statistics
 */
export async function getWhatsAppStats(): Promise<WhatsAppStats> {
  return apiRequest('/api/whatsapp/stats');
}

// ============= Webhooks =============

/**
 * Get incoming messages
 */
export async function getIncomingMessages(
  limit: number = 50,
  offset: number = 0,
  unprocessedOnly: boolean = false
): Promise<any[]> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
    unprocessed_only: unprocessedOnly.toString(),
  });

  return apiRequest(`/api/whatsapp/incoming-messages?${params}`);
}

/**
 * Mark incoming message as processed
 */
export async function markMessageProcessed(messageId: string): Promise<void> {
  return apiRequest(`/api/whatsapp/incoming-messages/${messageId}/mark-processed`, {
    method: 'POST',
  });
}
