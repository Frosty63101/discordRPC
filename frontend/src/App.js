import { useEffect, useState, useRef } from 'react';
import './App.css';

function App() {
  const [config, setConfig] = useState(null);
  const [books, setBooks] = useState({});
  const [selectedISBN, setSelectedISBN] = useState('');
  const [status, setStatus] = useState('');
  const [message, setMessage] = useState('');
  const [customScript, setCustomScript] = useState('');
  const [showEditor, setShowEditor] = useState(false);
  const intervalRef = useRef(null);
  const messageTimer = useRef(null);

  useEffect(() => {
    if (window.__GOODREADS_RPC_INITIALIZED__) return;
    window.__GOODREADS_RPC_INITIALIZED__ = true;

    fetch('http://localhost:5000/api/config')
      .then(res => res.json())
      .then(setConfig);

    fetch('http://localhost:5000/api/getStartByDefault')
      .then(res => res.json())
      .then(data => {
        if (data.startByDefault) {
          fetch('http://localhost:5000/api/presence/start', { method: 'POST' })
            .then(() => showMessage('✅ Presence started by default'));
        }
      });

    fetch('http://localhost:5000/api/scraper/get_books')
      .then(res => res.json())
      .then(([bookData, current]) => {
        setBooks(bookData);
        setSelectedISBN(current);
      });

    fetchCustomScript();

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
        const newStatus = Array.isArray(data.status) ? data.status.join(', ') : data.status;
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

  const exit = () => {
    fetch('http://localhost:5000/shutdown', { method: 'POST' })
      .then(() => {
        showMessage('🛑 Exiting...');
        setTimeout(() => {
          window.electron?.ipcRenderer?.send('force-quit');
        }, 2000);
      });
  };

  const fetchCustomScript = () => {
    fetch('http://localhost:5000/api/custom_script')
      .then(res => res.text())
      .then(setCustomScript);
  };

  const saveCustomScript = () => {
    fetch('http://localhost:5000/api/custom_script', {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body: customScript,
    }).then(() => {
      showMessage('✅ Custom script saved');
      setShowEditor(false);
    });
  };

  if (!config) return <div style={{ padding: '20px' }}>Loading configuration...</div>;

  return (
    <div style={{ padding: '24px', maxWidth: '800px', margin: '0 auto', fontFamily: 'Segoe UI, sans-serif', color: '#333' }}>
      <h1 style={{ marginBottom: '20px', color: '#444' }}>Goodreads Discord RPC</h1>

      <label>Discord App ID:</label>
      <input className="input" value={config.discord_app_id} onChange={e => {
        setConfig({ ...config, discord_app_id: e.target.value });
        saveConfig();
      }} />

      <label>Goodreads User ID:</label>
      <input className="input" value={config.goodreads_id} onChange={e => {
        setConfig({ ...config, goodreads_id: e.target.value });
        saveConfig();
      }} />

      <label>Update Interval (seconds):</label>
      <input type="number" className="input" value={config.update_interval} onChange={e => {
        setConfig({ ...config, update_interval: parseInt(e.target.value) });
        saveConfig();
      }} />

      <label>Currently Reading:</label>
      <select className="input" value={selectedISBN} onChange={e => {
        updateBook(e.target.value);
        saveConfig();
      }}>
        {Object.entries(books).map(([isbn, book]) => (
          <option key={isbn} value={isbn}>{book.title} by {book.author}</option>
        ))}
      </select>

      <label style={{ marginTop: '12px' }}>
        <input type="checkbox" checked={config.minimizeToTray} onChange={e => {
          setConfig({ ...config, minimizeToTray: e.target.checked });
          saveConfig();
        }} />
        {' '}Minimize to Tray
      </label>

      <label>
        <input type="checkbox" checked={config.startOnStartup} onChange={e => {
          setConfig({ ...config, startOnStartup: e.target.checked });
          saveConfig();
          fetch('http://localhost:5000/api/startup/enable', { method: 'POST' });
        }} />
        {' '}Start on Startup
      </label>

      <label>Presence Template (JSON):</label>
      <textarea className="input" rows={6} value={JSON.stringify(config.presence_template, null, 2)} onChange={e => {
        try {
          setConfig({ ...config, presence_template: JSON.parse(e.target.value) });
        } catch {}
      }} />

      <label>Custom Variables (JSON):</label>
      <textarea className="input" rows={4} value={JSON.stringify(config.custom_vars, null, 2)} onChange={e => {
        try {
          setConfig({ ...config, custom_vars: JSON.parse(e.target.value) });
        } catch {}
      }} />

      <div style={{ display: 'flex', gap: '10px', marginTop: '20px' }}>
        <button className="btn" onClick={saveConfig}>Save Config</button>
        <button className="btn" onClick={startPresence}>Start</button>
        <button className="btn" onClick={stopPresence}>Stop</button>
        <button className="btn" onClick={exit}>Exit</button>
        <button className="btn" onClick={() => setShowEditor(true)}>Edit custom_scraper.py</button>
      </div>

      <p style={{ marginTop: '10px' }}><strong>Status:</strong> {status}</p>
      {message && <p style={{ color: 'green', fontWeight: 'bold' }}>{message}</p>}

      {showEditor && (
        <div style={{
          position: 'fixed', top: 0, left: 0, width: '100%',
          height: '100%', backgroundColor: 'rgba(0,0,0,0.5)',
          display: 'flex', alignItems: 'center', justifyContent: 'center'
        }}>
          <div style={{ backgroundColor: '#fff', padding: '20px', width: '80%', height: '80%', overflow: 'auto' }}>
            <h3>Edit custom_scraper.py</h3>
            <textarea
              value={customScript}
              onChange={e => setCustomScript(e.target.value)}
              style={{ width: '100%', height: '80%', fontFamily: 'monospace' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '10px' }}>
              <button className="btn" onClick={saveCustomScript}>Save Script</button>
              <button className="btn" onClick={() => setShowEditor(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
