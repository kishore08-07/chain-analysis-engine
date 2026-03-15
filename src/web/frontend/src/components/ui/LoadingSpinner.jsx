import React from 'react';

export default function LoadingSpinner({ message = 'Loading analysis data...' }) {
  return (
    <div className="loading">
      <div className="spinner"></div>
      {message}
    </div>
  );
}
