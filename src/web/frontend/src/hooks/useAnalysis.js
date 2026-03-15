import { useState, useEffect, useCallback } from 'react';

export function useAnalysis() {
  const [files, setFiles] = useState([]);
  const [selFile, setSelFile] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch('/api/files')
      .then(r => r.json())
      .then(d => { setFiles(d.files || []); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  const loadFile = useCallback(stem => {
    setLoading(true);
    setSelFile(stem);
    setError(null);
    fetch(`/api/analysis/${stem}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  return { files, selFile, data, loading, error, loadFile };
}
