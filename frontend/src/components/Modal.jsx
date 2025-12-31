import { useState } from 'react'

/**
 * Alert Modal - Simple information/error display
 */
export function AlertModal({ isOpen, onClose, title, message, type = 'info' }) {
  if (!isOpen) return null

  const colors = {
    info: '#3b82f6',
    success: '#10b981',
    error: '#ef4444',
    warning: '#f59e0b'
  }

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0,0,0,0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000
    }}>
      <div style={{
        background: 'white',
        borderRadius: '8px',
        padding: '24px',
        maxWidth: '500px',
        width: '90%',
        boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)'
      }}>
        <h3 style={{
          margin: '0 0 16px 0',
          fontSize: '18px',
          fontWeight: '600',
          color: colors[type]
        }}>
          {title}
        </h3>
        <p style={{
          margin: '0 0 20px 0',
          color: '#64748b',
          whiteSpace: 'pre-wrap'
        }}>
          {message}
        </p>
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button
            className="btn btn-primary"
            onClick={onClose}
            autoFocus
          >
            OK
          </button>
        </div>
      </div>
    </div>
  )
}

/**
 * Confirm Modal - Yes/No confirmation dialog
 */
export function ConfirmModal({ isOpen, onClose, onConfirm, title, message, confirmText = 'Confirm', cancelText = 'Cancel', type = 'warning' }) {
  if (!isOpen) return null

  const handleConfirm = () => {
    onConfirm()
    onClose()
  }

  const colors = {
    info: '#3b82f6',
    warning: '#f59e0b',
    danger: '#ef4444'
  }

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0,0,0,0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000
    }}>
      <div style={{
        background: 'white',
        borderRadius: '8px',
        padding: '24px',
        maxWidth: '500px',
        width: '90%',
        boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)'
      }}>
        <h3 style={{
          margin: '0 0 16px 0',
          fontSize: '18px',
          fontWeight: '600',
          color: colors[type]
        }}>
          {title}
        </h3>
        <p style={{
          margin: '0 0 20px 0',
          color: '#64748b',
          whiteSpace: 'pre-wrap'
        }}>
          {message}
        </p>
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
          <button
            className="btn btn-secondary"
            onClick={onClose}
          >
            {cancelText}
          </button>
          <button
            className={`btn ${type === 'danger' ? 'btn-danger' : 'btn-primary'}`}
            onClick={handleConfirm}
            autoFocus
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  )
}

/**
 * Confirm with Text Input Modal - Requires user to type confirmation text
 */
export function ConfirmWithTextModal({ isOpen, onClose, onConfirm, title, message, confirmationText, placeholder }) {
  const [inputValue, setInputValue] = useState('')

  if (!isOpen) return null

  const handleConfirm = () => {
    if (inputValue === confirmationText) {
      onConfirm()
      onClose()
      setInputValue('')
    }
  }

  const handleClose = () => {
    onClose()
    setInputValue('')
  }

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0,0,0,0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000
    }}>
      <div style={{
        background: 'white',
        borderRadius: '8px',
        padding: '24px',
        maxWidth: '500px',
        width: '90%',
        boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)'
      }}>
        <h3 style={{
          margin: '0 0 16px 0',
          fontSize: '18px',
          fontWeight: '600',
          color: '#ef4444'
        }}>
          {title}
        </h3>
        <p style={{
          margin: '0 0 12px 0',
          color: '#64748b',
          whiteSpace: 'pre-wrap'
        }}>
          {message}
        </p>
        <p style={{ marginBottom: '12px', color: '#64748b' }}>
          Type <strong>{confirmationText}</strong> to confirm:
        </p>
        <input
          type="text"
          value={inputValue}
          onChange={e => setInputValue(e.target.value)}
          placeholder={placeholder || `Type "${confirmationText}" here`}
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #e2e8f0',
            borderRadius: '4px',
            marginBottom: '20px',
            fontSize: '14px'
          }}
          autoFocus
          onKeyPress={e => {
            if (e.key === 'Enter' && inputValue === confirmationText) {
              handleConfirm()
            }
          }}
        />
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
          <button
            className="btn btn-secondary"
            onClick={handleClose}
          >
            Cancel
          </button>
          <button
            className="btn btn-danger"
            onClick={handleConfirm}
            disabled={inputValue !== confirmationText}
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  )
}
