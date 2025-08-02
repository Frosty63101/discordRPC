import { useEffect, useState, useRef } from 'react';

function App() {
  const [config, setConfig] = useState(null);
  const [books, setBooks] = useState({});
  const [selectedISBN, setSelectedISBN] = useState('');
  const [status, setStatus] = useState('');
  const [message, setMessage] = useState('');
  const intervalRef = useRef(null);
  const messageTimer = useRef(null);

  useEffect(() => {
    // Prevent reinitialization in Electron
    if (window.__GOODREADS_RPC_INITIALIZED__) return;
    window.__GOODREADS_RPC_INITIALIZED__ = true;

    // Load config
    fetch('http://localhost:5000/api/config')
      .then(res => res.json())
      .then(setConfig);

    // Load books
    fetch('http://localhost:5000/api/scraper/get_books')
      .then(res => res.json())
      .then(([bookData, current]) => {
        setBooks(bookData);
        setSelectedISBN(current);
      });

    // Visibility-based status polling
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        fetchStatus();
        clearInterval(intervalRef.current);
        intervalRef.current = setInterval(fetchStatus, 10000);
      } else {
        clearInterval(intervalRef.current);
      }
    };

    handleVisibility();
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      clearInterval(intervalRef.current);
      document.removeEventListener('visibilitychange', handleVisibility);
      clearTimeout(messageTimer.current);
    };
  }, []);

  const fetchStatus = () => {
    fetch('http://localhost:5000/api/status')
      .then(res => res.json())
      .then(data => {
        const newStatus = Array.isArray(data.status)
          ? data.status.join(', ')
          : data.status;
        setStatus(newStatus);
      });
  };

  const showMessage = msg => {
    setMessage(msg);
    clearTimeout(messageTimer.current);
    messageTimer.current = setTimeout(() => setMessage(''), 3000);
  };

  const saveConfig = () => {
    fetch('http://localhost:5000/api/config/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    }).then(() => showMessage('✅ Config saved'));
  };

  const updateBook = isbn => {
    setSelectedISBN(isbn);
    fetch('http://localhost:5000/api/book/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ isbn }),
    }).then(() => showMessage('✅ Book updated'));
  };

  const startPresence = () => {
    fetch('http://localhost:5000/api/presence/start', { method: 'POST' })
      .then(() => showMessage('✅ Presence started'));
  };

  const stopPresence = () => {
    fetch('http://localhost:5000/api/presence/stop', { method: 'POST' })
      .then(() => showMessage('🛑 Presence stopped'));
  };

  if (!config) return <div style={{ padding: '20px' }}>Loading configuration...</div>;

  return (
    <div style={{
      padding: '24px',
      maxWidth: '600px',
      margin: '0 auto',
      fontFamily: 'Segoe UI, sans-serif',
      color: '#333',
    }}>
      <h1 style={{ marginBottom: '20px', color: '#444' }}>Goodreads Discord RPC</h1>

      <label>Discord App ID:</label>
      <input
        className="input"
        value={config.discord_app_id}
        onChange={e => setConfig({ ...config, discord_app_id: e.target.value })}
      />

      <label>Goodreads User ID:</label>
      <input
        className="input"
        value={config.goodreads_id}
        onChange={e => setConfig({ ...config, goodreads_id: e.target.value })}
      />

      <label>Update Interval (seconds):</label>
      <input
        type="number"
        className="input"
        value={config.update_interval}
        onChange={e => setConfig({ ...config, update_interval: parseInt(e.target.value) })}
      />

      <label>Currently Reading:</label>
      <select
        className="input"
        value={selectedISBN}
        onChange={e => updateBook(e.target.value)}
      >
        {Object.entries(books).map(([isbn, book]) => (
          <option key={isbn} value={isbn}>
            {book.title} by {book.author}
          </option>
        ))}
      </select>

      <label style={{ marginTop: '12px' }}>
        <input
          type="checkbox"
          checked={config.minimizeToTray}
          onChange={e =>
            setConfig({ ...config, minimizeToTray: e.target.checked })
          }
        />
        {' '}Minimize to Tray
      </label>

      <label>
        <input
          type="checkbox"
          checked={config.startOnStartup}
          onChange={e =>
            setConfig({ ...config, startOnStartup: e.target.checked })
          }
        />
        {' '}Start on Startup
      </label>

      <div style={{ display: 'flex', gap: '10px', marginTop: '20px' }}>
        <button className="btn" onClick={saveConfig}>Save Config</button>
        <button className="btn" onClick={startPresence}>Start</button>
        <button className="btn" onClick={stopPresence}>Stop</button>
      </div>

      <p style={{ marginTop: '10px' }}><strong>Status:</strong> {status}</p>
      {message && (
        <p style={{ color: 'green', fontWeight: 'bold' }}>{message}</p>
      )}

      <style>{`
        .input {
          width: 100%;
          padding: 8px;
          margin-bottom: 12px;
          font-size: 16px;
          border: 1px solid #ccc;
          border-radius: 6px;
          box-sizing: border-box;
        }

        .btn {
          padding: 10px 14px;
          font-size: 14px;
          background: #007acc;
          color: white;
          border: none;
          border-radius: 6px;
          cursor: pointer;
        }

        .btn:hover {
          background: #005fa3;
        }
      `}</style>
    </div>
  );
}

export default App;
