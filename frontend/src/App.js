import { useEffect, useState, useRef, useCallback } from 'react';
import './App.css';

function App() {
  const [config, setConfig] = useState(null);
  const [books, setBooks] = useState({});
  const [selectedISBN, setSelectedISBN] = useState('');
  const [status, setStatus] = useState('');
  const [message, setMessage] = useState('');
  const intervalRef = useRef(null);
  const messageTimer = useRef(null);

  const fetchStatus = useCallback(() => {
    fetch('http://localhost:5000/api/status')
      .then(res => res.json())
      .then(data => {
        // Backend returns arrays (status/message/lastUpdated)
        const newStatus = Array.isArray(data.status) ? data.status.join(', ') : data.status;
        setStatus(newStatus || '');
      })
      .catch(() => {});
  }, []);

  const showMessage = (msg) => {
    setMessage(msg);
    clearTimeout(messageTimer.current);
    messageTimer.current = setTimeout(() => setMessage(''), 2500);
  };

  const loadBooks = useCallback(() => {
    fetch('http://localhost:5000/api/scraper/get_books')
      .then(res => res.json())
      .then(([bookData, current]) => {
        setBooks(bookData || {});
        setSelectedISBN(current || '');
      })
      .then(() => fetchStatus())
      .catch(() => {});
  }, [fetchStatus]);

  useEffect(() => {
    if (window.__GOODREADS_RPC_INITIALIZED__) return;
    window.__GOODREADS_RPC_INITIALIZED__ = true;

    fetch('http://localhost:5000/api/config')
      .then(res => res.json())
      .then(setConfig)
      .catch(() => {});

    fetch('http://localhost:5000/api/getStartByDefault')
      .then(res => res.json())
      .then(data => {
        if (data.startByDefault) {
          fetch('http://localhost:5000/api/presence/start', { method: 'POST' })
            .then(() => showMessage('✅ Presence started by default'))
            .catch(() => {});
        }
      })
      .catch(() => {});

    loadBooks();

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
  }, [fetchStatus, loadBooks]);

  const saveConfig = () => {
    if (!config) return;
    fetch('http://localhost:5000/api/config/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    })
      .then(() => showMessage('✅ Config saved'))
      .then(fetchStatus)
      .catch(() => {});
  };

  const updateBook = (isbn) => {
    setSelectedISBN(isbn);
    fetch('http://localhost:5000/api/book/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ isbn }),
    })
      .then(() => showMessage('✅ Book updated'))
      .then(fetchStatus)
      .catch(() => {});
  };

  const startPresence = () => {
    fetch('http://localhost:5000/api/presence/start', { method: 'POST' })
      .then(() => showMessage('✅ Presence started'))
      .then(fetchStatus)
      .catch(() => {});
  };

  const stopPresence = () => {
    fetch('http://localhost:5000/api/presence/stop', { method: 'POST' })
      .then(() => showMessage('🛑 Presence stopped'))
      .then(fetchStatus)
      .catch(() => {});
  };

  const exit = () => {
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), 800);
    fetch('http://localhost:5000/shutdown', { method: 'POST', signal: controller.signal })
      .catch(() => {})
      .finally(() => clearTimeout(t));

    showMessage('🛑 Exiting...');
    window.electron?.ipcRenderer?.send('force-quit');
  };

  const onPlatformChange = (newPlatform) => {
    // Update config, save, then reload books from that platform
    const updated = { ...config, platform: newPlatform };
    setConfig(updated);

    fetch('http://localhost:5000/api/config/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updated),
    })
      .then(() => showMessage(`✅ Switched to ${newPlatform}`))
      .then(() => loadBooks())
      .catch(() => {});
  };

  if (!config) return <div style={{ padding: '20px' }}>Loading configuration...</div>;

  const platform = (config.platform || 'goodreads').toLowerCase();

  return (
    <div style={{
      padding: '24px',
      maxWidth: '600px',
      margin: '0 auto',
      fontFamily: 'Segoe UI, sans-serif',
      color: '#333',
    }}>
      <h1 style={{ marginBottom: '20px', color: '#444' }}>Reading Discord RPC</h1>

      <label>Platform:</label>
      <select
        className="input"
        value={platform}
        onChange={e => onPlatformChange(e.target.value)}
      >
        <option value="goodreads">Goodreads</option>
        <option value="storygraph">StoryGraph</option>
      </select>

      <label>Discord App ID:</label>
      <input
        className="input"
        value={config.discord_app_id || ''}
        onChange={e => setConfig({ ...config, discord_app_id: e.target.value })}
        onBlur={() => { saveConfig(); fetchStatus(); }}
      />

      {platform === 'goodreads' && (
        <>
          <label>Goodreads User ID:</label>
          <input
            className="input"
            value={config.goodreads_id || ''}
            onChange={e => setConfig({ ...config, goodreads_id: e.target.value })}
            onBlur={() => { saveConfig(); loadBooks(); }}
          />
        </>
      )}

      {platform === 'storygraph' && (
        <>
          <label>StoryGraph Username:</label>
          <input
            className="input"
            value={config.storygraph_username || ''}
            onChange={e => setConfig({ ...config, storygraph_username: e.target.value })}
            onBlur={() => { saveConfig(); loadBooks(); }}
          />

          <div style={{ fontSize: '13px', marginTop: '6px', color: '#777' }}>
            Note: StoryGraph often blocks automated scraping (your HTTP 436).
            If books don’t load, you’ll need a headless-browser approach (Playwright) or a manual import method.
          </div>
        </>
      )}

      <label>Update Interval (seconds):</label>
      <input
        type="number"
        className="input"
        value={config.update_interval ?? 60}
        onChange={e => {
          const val = parseInt(e.target.value, 10);
          setConfig({ ...config, update_interval: Number.isNaN(val) ? 60 : val });
        }}
        onBlur={() => { saveConfig(); fetchStatus(); }}
      />

      <label>Currently Reading:</label>
      <select
        className="input"
        value={selectedISBN}
        onChange={e => {
          updateBook(e.target.value);
          saveConfig();
          fetchStatus();
        }}
        disabled={Object.keys(books).length === 0}
      >
        {Object.keys(books).length === 0 ? (
          <option value="">No books found</option>
        ) : (
          Object.entries(books).map(([isbn, book]) => (
            <option key={isbn} value={isbn}>
              {book.title} by {book.author}
            </option>
          ))
        )}
      </select>

      <div style={{ display: 'flex', gap: '10px', marginTop: '12px' }}>
        <button className="btn" onClick={loadBooks}>Refresh Books</button>
      </div>

      <label style={{ marginTop: '12px' }}>
        <input
          type="checkbox"
          checked={!!config.minimizeToTray}
          onChange={e => setConfig({ ...config, minimizeToTray: e.target.checked })}
          onBlur={() => { saveConfig(); fetchStatus(); }}
        />
        {' '}Minimize to Tray
      </label>

      <label>
        <input
          type="checkbox"
          checked={!!config.startOnStartup}
          onChange={e => setConfig({ ...config, startOnStartup: e.target.checked })}
          onBlur={() => {
            saveConfig();
            fetch('http://localhost:5000/api/startup/enable', { method: 'POST' }).catch(() => {});
            fetchStatus();
          }}
        />
        {' '}Start on Startup
      </label>

      <div style={{ display: 'flex', gap: '10px', marginTop: '20px' }}>
        <button className="btn" onClick={saveConfig}>Save Config</button>
        <button className="btn" onClick={startPresence}>Start</button>
        <button className="btn" onClick={stopPresence}>Stop</button>
        <button className="btn" onClick={exit}>Exit</button>
      </div>

      <p style={{ marginTop: '10px' }}><strong>Status:</strong> {status}</p>
      {message && <p style={{ color: 'green', fontWeight: 'bold' }}>{message}</p>}
    </div>
  );
}

export default App;
