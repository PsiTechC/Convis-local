'use client';

import { useState, useCallback, useRef } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface ImportedNode {
  id: string;
  name: string;
  type: string;
  original_type: string;
  position: { x: number; y: number };
}

interface ImportedConnection {
  from_node: string;
  to_node: string;
  from_output: string;
  to_input: string;
}

interface CredentialInfo {
  name: string;
  type: string;
  n8n_type?: string;
}

interface NodeInfo {
  name: string;
  type: string;
  mapped_to: string;
}

interface ValidationResult {
  success: boolean;
  valid: boolean;
  message: string;
  preview: {
    name: string;
    node_count: number;
    connection_count: number;
    nodes_by_category: Record<string, NodeInfo[]>;
    credentials_required: CredentialInfo[];
  };
}

interface ImportResult {
  success: boolean;
  workflow_id: string;
  workflow_name: string;
  node_count: number;
  edge_count: number;
  credentials_required: CredentialInfo[];
  is_active: boolean;
  message: string;
  next_steps?: (string | null)[];
}

interface N8nImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImportComplete: (workflow: ImportResult) => void;
  isDarkMode: boolean;
}

// Icons
const UploadIcon = () => (
  <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
  </svg>
);

const CheckIcon = () => (
  <svg className="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
  </svg>
);

const WarningIcon = () => (
  <svg className="w-5 h-5 text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
  </svg>
);

const ErrorIcon = () => (
  <svg className="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
  </svg>
);

const XIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
  </svg>
);

const LoaderIcon = ({ className = "w-5 h-5 animate-spin" }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
  </svg>
);

const N8nIcon = () => (
  <svg className="w-8 h-8" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
  </svg>
);

const NodeIcon = ({ type }: { type: string }) => {
  const iconClass = "w-4 h-4";

  switch (type) {
    case 'trigger':
      return <svg className={iconClass} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>;
    case 'action':
      return <svg className={iconClass} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
    case 'condition':
      return <svg className={iconClass} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
    case 'transform':
      return <svg className={iconClass} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>;
    default:
      return <svg className={iconClass} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16m-7 6h7" /></svg>;
  }
};

export function N8nImportModal({ isOpen, onClose, onImportComplete, isDarkMode }: N8nImportModalProps) {
  const [step, setStep] = useState<'upload' | 'preview' | 'importing' | 'complete'>('upload');
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [jsonContent, setJsonContent] = useState<string>('');
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const resetState = useCallback(() => {
    setStep('upload');
    setSelectedFile(null);
    setJsonContent('');
    setValidationResult(null);
    setImportResult(null);
    setError('');
    setIsLoading(false);
    setDragActive(false);
  }, []);

  const handleClose = useCallback(() => {
    resetState();
    onClose();
  }, [onClose, resetState]);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  }, []);

  const handleFile = async (file: File) => {
    if (!file.name.endsWith('.json')) {
      setError('Please upload a JSON file');
      return;
    }

    setSelectedFile(file);
    setError('');
    setIsLoading(true);

    try {
      const content = await file.text();
      setJsonContent(content);

      // Validate the workflow
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/workflows/import/n8n/validate`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: content,
      });

      if (response.ok) {
        const result = await response.json();
        setValidationResult(result);
        setStep('preview');
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to validate workflow');
      }
    } catch (err) {
      setError('Failed to read file or validate workflow');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0]);
    }
  };

  const handleImport = async () => {
    if (!jsonContent) return;

    setStep('importing');
    setIsLoading(true);
    setError('');

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/workflows/import/n8n`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: jsonContent,
      });

      if (response.ok) {
        const result = await response.json();
        setImportResult(result);
        setStep('complete');
        onImportComplete(result);
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to import workflow');
        setStep('preview');
      }
    } catch (err) {
      setError('Failed to import workflow');
      console.error(err);
      setStep('preview');
    } finally {
      setIsLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="fixed inset-0 bg-black/50" onClick={handleClose} />

        <div className={`relative rounded-xl shadow-xl max-w-2xl w-full ${isDarkMode ? 'bg-gray-800' : 'bg-white'}`}>
          {/* Header */}
          <div className={`flex items-center justify-between p-6 border-b ${isDarkMode ? 'border-gray-700' : 'border-gray-200'}`}>
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg ${isDarkMode ? 'bg-orange-900/30 text-orange-400' : 'bg-orange-100 text-orange-600'}`}>
                <N8nIcon />
              </div>
              <div>
                <h2 className={`text-lg font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                  Import n8n Workflow
                </h2>
                <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                  Upload your n8n workflow JSON to convert it to Convis format
                </p>
              </div>
            </div>
            <button
              onClick={handleClose}
              className={`p-2 rounded-lg transition-colors ${isDarkMode ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-100 text-gray-500'}`}
            >
              <XIcon />
            </button>
          </div>

          {/* Content */}
          <div className="p-6">
            {/* Error Message */}
            {error && (
              <div className={`mb-4 p-4 rounded-lg border ${isDarkMode ? 'bg-red-900/20 border-red-900/30 text-red-400' : 'bg-red-50 border-red-200 text-red-600'}`}>
                <div className="flex items-center gap-2">
                  <ErrorIcon />
                  <span>{error}</span>
                </div>
              </div>
            )}

            {/* Step: Upload */}
            {step === 'upload' && (
              <div
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                className={`border-2 border-dashed rounded-xl p-12 text-center transition-colors ${
                  dragActive
                    ? isDarkMode ? 'border-orange-500 bg-orange-900/20' : 'border-orange-500 bg-orange-50'
                    : isDarkMode ? 'border-gray-600 hover:border-gray-500' : 'border-gray-300 hover:border-gray-400'
                }`}
              >
                {isLoading ? (
                  <div className="flex flex-col items-center">
                    <LoaderIcon className="w-12 h-12 text-orange-500 animate-spin" />
                    <p className={`mt-4 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                      Validating workflow...
                    </p>
                  </div>
                ) : (
                  <>
                    <div className={`mx-auto mb-4 ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                      <UploadIcon />
                    </div>
                    <h3 className={`text-lg font-medium mb-2 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                      Drop your n8n workflow JSON here
                    </h3>
                    <p className={`mb-4 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                      or click to browse
                    </p>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".json"
                      onChange={handleFileInput}
                      className="hidden"
                    />
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="px-6 py-3 bg-orange-600 hover:bg-orange-700 text-white rounded-lg font-medium transition-colors"
                    >
                      Select File
                    </button>
                    <p className={`mt-4 text-sm ${isDarkMode ? 'text-gray-500' : 'text-gray-400'}`}>
                      Export your workflow from n8n: Settings &rarr; Download
                    </p>
                  </>
                )}
              </div>
            )}

            {/* Step: Preview */}
            {step === 'preview' && validationResult && validationResult.preview && (
              <div className="space-y-6">
                {/* Workflow Info */}
                <div className={`p-4 rounded-lg ${isDarkMode ? 'bg-gray-700' : 'bg-gray-100'}`}>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className={`font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                      {validationResult.preview.name}
                    </h3>
                    <span className={`px-3 py-1 rounded-full text-sm ${
                      validationResult.valid
                        ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                        : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                    }`}>
                      {validationResult.valid ? 'Valid' : 'Invalid'}
                    </span>
                  </div>
                  <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                    {validationResult.preview.node_count} nodes &bull; {validationResult.preview.connection_count} connections
                  </p>
                </div>

                {/* Nodes Preview by Category */}
                <div>
                  <h4 className={`font-medium mb-3 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                    Nodes to Import
                  </h4>
                  <div className={`max-h-64 overflow-y-auto rounded-lg border ${isDarkMode ? 'border-gray-700' : 'border-gray-200'}`}>
                    {Object.entries(validationResult.preview.nodes_by_category).map(([category, nodes], catIndex) => (
                      <div key={category}>
                        <div className={`px-3 py-2 font-medium text-sm ${isDarkMode ? 'bg-gray-800 text-gray-300' : 'bg-gray-50 text-gray-700'}`}>
                          {category} ({nodes.length})
                        </div>
                        {nodes.map((node, index) => (
                          <div
                            key={`${category}-${index}`}
                            className={`flex items-center gap-3 p-3 ${
                              index !== nodes.length - 1
                                ? isDarkMode ? 'border-b border-gray-700' : 'border-b border-gray-200'
                                : ''
                            }`}
                          >
                            <div className={`p-1.5 rounded ${
                              category === 'Triggers' ? 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400' :
                              category === 'Actions' ? 'bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400' :
                              category === 'Logic' ? 'bg-yellow-100 text-yellow-600 dark:bg-yellow-900/30 dark:text-yellow-400' :
                              'bg-purple-100 text-purple-600 dark:bg-purple-900/30 dark:text-purple-400'
                            }`}>
                              <NodeIcon type={category.toLowerCase()} />
                            </div>
                            <div className="flex-1">
                              <p className={`font-medium ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                                {node.name}
                              </p>
                              <p className={`text-xs ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                                {node.type} &rarr; {node.mapped_to}
                              </p>
                            </div>
                            <CheckIcon />
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Credentials Required */}
                {validationResult.preview.credentials_required?.length > 0 && (
                  <div>
                    <h4 className={`font-medium mb-3 flex items-center gap-2 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                      <WarningIcon />
                      Credentials to Configure
                    </h4>
                    <div className={`p-4 rounded-lg ${isDarkMode ? 'bg-yellow-900/20 border border-yellow-900/30' : 'bg-yellow-50 border border-yellow-200'}`}>
                      <ul className={`space-y-1 text-sm ${isDarkMode ? 'text-yellow-400' : 'text-yellow-700'}`}>
                        {validationResult.preview.credentials_required.map((cred, index) => (
                          <li key={index}>
                            &bull; {cred.name} ({cred.type})
                          </li>
                        ))}
                      </ul>
                      <p className={`mt-2 text-xs ${isDarkMode ? 'text-yellow-500' : 'text-yellow-600'}`}>
                        You&apos;ll need to configure these integrations after import
                      </p>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Step: Importing */}
            {step === 'importing' && (
              <div className="text-center py-12">
                <LoaderIcon className="w-16 h-16 text-orange-500 animate-spin mx-auto" />
                <h3 className={`text-lg font-medium mt-4 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                  Importing Workflow...
                </h3>
                <p className={`mt-2 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                  Converting nodes and connections to Convis format
                </p>
              </div>
            )}

            {/* Step: Complete */}
            {step === 'complete' && importResult && (
              <div className="space-y-6">
                <div className="text-center">
                  <div className="w-16 h-16 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center mx-auto mb-4">
                    <CheckIcon />
                  </div>
                  <h3 className={`text-xl font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                    Workflow Imported!
                  </h3>
                  <p className={`mt-2 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                    &quot;{importResult.workflow_name}&quot; with {importResult.node_count} nodes
                  </p>
                </div>

                {importResult.credentials_required?.length > 0 && (
                  <div className={`p-4 rounded-lg ${isDarkMode ? 'bg-yellow-900/20 border border-yellow-900/30' : 'bg-yellow-50 border border-yellow-200'}`}>
                    <h4 className={`font-medium mb-2 flex items-center gap-2 ${isDarkMode ? 'text-yellow-400' : 'text-yellow-700'}`}>
                      <WarningIcon />
                      Next Steps
                    </h4>
                    <p className={`text-sm ${isDarkMode ? 'text-yellow-400' : 'text-yellow-700'}`}>
                      Configure these integrations to complete setup:
                    </p>
                    <ul className={`mt-2 space-y-1 text-sm ${isDarkMode ? 'text-yellow-400' : 'text-yellow-700'}`}>
                      {importResult.credentials_required.map((cred, index) => (
                        <li key={index}>&bull; {cred.name} ({cred.type})</li>
                      ))}
                    </ul>
                  </div>
                )}

                {importResult.next_steps?.filter(Boolean).length > 0 && (
                  <div className={`p-4 rounded-lg ${isDarkMode ? 'bg-blue-900/20 border border-blue-900/30' : 'bg-blue-50 border border-blue-200'}`}>
                    <h4 className={`font-medium mb-2 ${isDarkMode ? 'text-blue-400' : 'text-blue-700'}`}>
                      Recommended Actions
                    </h4>
                    <ul className={`space-y-1 text-sm ${isDarkMode ? 'text-blue-400' : 'text-blue-700'}`}>
                      {importResult.next_steps.filter(Boolean).map((step, index) => (
                        <li key={index}>&bull; {step}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className={`flex items-center justify-between p-6 border-t ${isDarkMode ? 'border-gray-700' : 'border-gray-200'}`}>
            {step === 'upload' && (
              <button
                onClick={handleClose}
                className={`px-4 py-2 rounded-lg transition-colors ${isDarkMode ? 'hover:bg-gray-700 text-gray-300' : 'hover:bg-gray-100 text-gray-700'}`}
              >
                Cancel
              </button>
            )}

            {step === 'preview' && (
              <>
                <button
                  onClick={resetState}
                  className={`px-4 py-2 rounded-lg transition-colors ${isDarkMode ? 'hover:bg-gray-700 text-gray-300' : 'hover:bg-gray-100 text-gray-700'}`}
                >
                  Upload Different File
                </button>
                <button
                  onClick={handleImport}
                  disabled={!validationResult?.valid || isLoading}
                  className="px-6 py-2 bg-orange-600 hover:bg-orange-700 disabled:bg-orange-400 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
                >
                  Import Workflow
                </button>
              </>
            )}

            {step === 'importing' && (
              <div className="w-full text-center">
                <span className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                  Please wait...
                </span>
              </div>
            )}

            {step === 'complete' && (
              <>
                <button
                  onClick={resetState}
                  className={`px-4 py-2 rounded-lg transition-colors ${isDarkMode ? 'hover:bg-gray-700 text-gray-300' : 'hover:bg-gray-100 text-gray-700'}`}
                >
                  Import Another
                </button>
                <button
                  onClick={handleClose}
                  className="px-6 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg font-medium transition-colors"
                >
                  Done
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
