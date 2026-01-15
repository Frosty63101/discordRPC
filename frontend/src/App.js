import { useEffect, useState, useRef, useCallback } from 'react';
import './App.css';

const apiBaseUrl = 'http://localhost:5000';

function App() {
  const [config, setConfig] = useState(null);
  const [books, setBooks] = useState({});
  const [selectedISBN, setSelectedISBN] = useState('');
  const [status, setStatus] = useState({ level: 'Idle', text: '', ts: null });
  const [statusLog, setStatusLog] = useState([]);
  const [message, setMessage] = useState('');

  const intervalRef = useRef(null);
  const messageTimer = useRef(null);

  const showMessage = useCallback((msg) => {
    setMessage(msg);
    clearTimeout(messageTimer.current);
    messageTimer.current = setTimeout(() => setMessage(''), 2500);
  }, []);

  const fetchStatus = useCallback(() => {
    fetch(`${apiBaseUrl}/api/status`)
      .then((res) => res.json())
      .then((data) => {
        const statusArr = Array.isArray(data?.status) ? data.status : [data?.status];
        const messageArr = Array.isArray(data?.message) ? data.message : [data?.message];
        const tsArr = Array.isArray(data?.lastUpdated) ? data.lastUpdated : [data?.lastUpdated];

        const eventCount = Math.max(statusArr.length, messageArr.length, tsArr.length);
        const events = [];

        for (let i = 0; i < eventCount; i++) {
          const level = statusArr[i] ?? null;
          const text = messageArr[i] ?? null;
          const ts = tsArr[i] ?? null;
          if (!level && !text) continue;

          events.push({
            level: typeof level === 'string' ? level : String(level),
            text: text == null ? '' : String(text),
            ts: typeof ts === 'number' ? ts : (ts ? Number(ts) : null),
          });
        }

        if (events.length === 0) return;

        const priority = { error: 3, active: 2, info: 1, idle: 0 };

        const current = [...events].reduce((best, ev) => {
          const bestScore = priority[(best.level || '').toLowerCase()] ?? 0;
          const evScore = priority[(ev.level || '').toLowerCase()] ?? 0;

          if (evScore > bestScore) return ev;
          if (evScore === bestScore) {
            const bestTs = best.ts ?? 0;
            const evTs = ev.ts ?? 0;
            if (evTs >= bestTs) return ev;
          }
          return best;
        }, events[0]);

        setStatus((prev) => {
          const next = {
            level: current.level || 'Idle',
            text: current.text || '',
            ts: current.ts || Date.now() / 1000,
          };
          if (prev.level === next.level && prev.text === next.text) return prev;
          return next;
        });

        setStatusLog((prev) => {
          const merged = [...prev, ...events].filter((ev, idx, arr) => {
            if (idx === 0) return true;
            const p = arr[idx - 1];
            return !(p.level === ev.level && p.text === ev.text && p.ts === ev.ts);
          });
          return merged.slice(-30);
        });
      })
      .catch(() => {});
  }, []);

  const burstPollStatus = useCallback(() => {
    fetchStatus();
    setTimeout(fetchStatus, 400);
    setTimeout(fetchStatus, 900);
    setTimeout(fetchStatus, 1600);
  }, [fetchStatus]);

  const fetchConfig = useCallback(() => {
    return fetch(`${apiBaseUrl}/api/config`)
      .then((res) => res.json())
      .then((cfg) => {
        setConfig(cfg);
        return cfg;
      })
      .catch(() => null);
  }, []);

  const fetchBooks = useCallback(() => {
    return fetch(`${apiBaseUrl}/api/scraper/get_books`)
      .then((res) => res.json())
      .then(([bookData, current]) => {
        setBooks(bookData || {});
        setSelectedISBN(current || '');
        return { bookData, current };
      })
      .catch(() => null);
  }, []);

  const saveConfig = useCallback(
    (nextConfig) => {
      const cfgToSave = nextConfig ?? config;
      if (!cfgToSave) return Promise.resolve(false);

      return fetch(`${apiBaseUrl}/api/config/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfgToSave),
      })
        .then(async (res) => {
          if (!res.ok) throw new Error('save failed');
          const fresh = await fetch(`${apiBaseUrl}/api/config`).then((r) => r.json());
          setConfig(fresh);
          showMessage('### Config saved');
          return true;
        })
        .then(() => burstPollStatus())
        .catch(() => false);
    },
    [config, burstPollStatus, showMessage]
  );

  const updateBook = useCallback(
    (isbn) => {
      setSelectedISBN(isbn);
      return fetch(`${apiBaseUrl}/api/book/select`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ isbn }),
      })
        .then((res) => {
          if (!res.ok) throw new Error('Book select failed');
          showMessage('### Book updated');
        })
        .then(() => burstPollStatus())
        .catch(() => {});
    },
    [burstPollStatus, showMessage]
  );

  const handlePlatformChange = useCallback(
    (newPlatform) => {
      if (!config) return;

      const updated = { ...config, platform: newPlatform, current_isbn: null };
      setConfig(updated);

      saveConfig(updated)
        .then(() => fetchBooks())
        .then(() => showMessage(`### Switched to ${newPlatform}`))
        .then(() => burstPollStatus())
        .catch(() => {});
    },
    [config, saveConfig, fetchBooks, burstPollStatus, showMessage]
  );

  const startPresence = useCallback(() => {
    fetch(`${apiBaseUrl}/api/presence/start`, { method: 'POST' })
      .then((res) => {
        if (!res.ok) throw new Error('start failed');
        showMessage('### Presence started');
      })
      .then(() => burstPollStatus())
      .catch(() => {});
  }, [burstPollStatus, showMessage]);

  const stopPresence = useCallback(() => {
    fetch(`${apiBaseUrl}/api/presence/stop`, { method: 'POST' })
      .then((res) => {
        if (!res.ok) throw new Error('stop failed');
        showMessage('!!! Presence stopped');
      })
      .then(() => burstPollStatus())
      .catch(() => {});
  }, [burstPollStatus, showMessage]);

  const exit = useCallback(() => {
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), 800);

    fetch(`${apiBaseUrl}/shutdown`, { method: 'POST', signal: controller.signal })
      .catch(() => {})
      .finally(() => clearTimeout(t));

    showMessage('!!! Exiting...');
    window.electron?.ipcRenderer?.send('force-quit');
  }, [showMessage]);

  useEffect(() => {
    if (window.__GOODREADS_RPC_INITIALIZED__) return;
    window.__GOODREADS_RPC_INITIALIZED__ = true;

    fetchConfig()
      .then(() => fetchBooks())
      .then(() => burstPollStatus())
      .catch(() => {});

    fetch(`${apiBaseUrl}/api/getStartByDefault`)
      .then((res) => res.json())
      .then((data) => {
        if (data.startByDefault) {
          fetch(`${apiBaseUrl}/api/presence/start`, { method: 'POST' })
            .then(() => showMessage('### Presence started by default'))
            .then(() => burstPollStatus())
            .catch(() => {});
        }
      })
      .catch(() => {});

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
  }, [fetchStatus, fetchConfig, fetchBooks, burstPollStatus, showMessage]);

  if (!config) return <div style={{ padding: '20px' }}>Loading configuration...</div>;

  const platform = (config.platform || 'goodreads').toLowerCase();

  return (
    <div
      style={{
        padding: '24px',
        maxWidth: '600px',
        margin: '0 auto',
        fontFamily: 'Segoe UI, sans-serif',
        color: '#333',
      }}
    >
      <h1 style={{ marginBottom: '20px', color: '#444' }}>Reading Discord RPC</h1>

      <label>Platform:</label>
      <select className="input" value={platform} onChange={(e) => handlePlatformChange(e.target.value)}>
        <option value="goodreads">Goodreads</option>
        <option value="storygraph">StoryGraph</option>
      </select>

      <label>Discord App ID:</label>
      <input
        className="input"
        value={config.discord_app_id || ''}
        onChange={(e) => setConfig({ ...config, discord_app_id: e.target.value ? e.target.value : '' })}
        onBlur={() => {
          saveConfig();
          burstPollStatus();
        }}
      />

      {platform === 'goodreads' && (
        <>
          <label>Goodreads User ID:</label>
          <input
            className="input"
            value={config.goodreads_id || ''}
            onChange={(e) => setConfig({ ...config, goodreads_id: e.target.value ? e.target.value : '' })}
            onBlur={() => {
              saveConfig();
              fetchBooks().then(() => burstPollStatus());
            }}
          />
        </>
      )}

      {platform === 'storygraph' && (
        <>
          <label>StoryGraph Username:</label>
          <input
            className="input"
            value={config.storygraph_username || ''}
            onChange={(e) => setConfig({ ...config, storygraph_username: e.target.value ? e.target.value : '' })}
            onBlur={() => {
              saveConfig();
              fetchBooks().then(() => burstPollStatus());
            }}
          />

          <label>StoryGraph Login Cookie (remember_user_token):</label>
          <input
            className="input"
            value={config.storygraph_remember_user_token || ''}
            placeholder="Paste remember_user_token here"
            onChange={(e) => setConfig({ ...config, storygraph_remember_user_token: e.target.value ? e.target.value : '' })}
            onBlur={() => {
              saveConfig();
              fetchBooks().then(() => burstPollStatus());
            }}
          />

          <small style={{ display: 'block', marginTop: '6px', color: '#666' }}>
            Paste the value of the <code style={{ marginLeft: '6px' }}>remember_user_token</code> cookie from app.thestorygraph.com.
          </small>
        </>
      )}

      <label>Update Interval (seconds):</label>
      <input
        type="number"
        className="input"
        value={config.update_interval ?? 60}
        onChange={(e) => {
          const val = Math.max(Math.min(parseInt(e.target.value, 10), 600), 60);
          setConfig({ ...config, update_interval: Number.isNaN(val) ? 60 : val });
        }}
        onBlur={() => {
          saveConfig();
          burstPollStatus();
        }}
      />

      <label>Currently Reading:</label>
      <select
        className="input"
        value={selectedISBN}
        onChange={(e) => {
          const next = e.target.value;
          setSelectedISBN(next);
          setConfig((prev) => ({ ...prev, current_isbn: next }));
          updateBook(next);
        }}
      >
        {Object.entries(books).map(([isbn, book]) => (
          <option key={isbn} value={isbn}>
            {book.title} by {book.author}
          </option>
        ))}
      </select>

      <div style={{ marginTop: '12px' }}>
        <label>
          <input
            type="checkbox"
            checked={!!config.minimizeToTray}
            onChange={(e) => setConfig({ ...config, minimizeToTray: e.target.checked })}
            onBlur={() => {
              saveConfig();
              burstPollStatus();
            }}
          />{' '}
          Minimize to Tray
        </label>
      </div>

      <div>
        <label>
          <input
            type="checkbox"
            checked={!!config.startOnStartup}
            onChange={(e) => setConfig({ ...config, startOnStartup: e.target.checked })}
            onBlur={() => {
              saveConfig();
              fetch(`${apiBaseUrl}/api/startup/enable`, { method: 'POST' }).catch(() => {});
              burstPollStatus();
            }}
          />{' '}
          Start on Startup
        </label>
      </div>

      <div style={{ display: 'flex', gap: '10px', marginTop: '20px' }}>
        <button className="btn" onClick={() => saveConfig()}>
          Save Config
        </button>
        <button className="btn" onClick={startPresence}>
          Start
        </button>
        <button className="btn" onClick={stopPresence}>
          Stop
        </button>
        <button className="btn" onClick={exit}>
          Exit
        </button>
      </div>

      <p style={{ marginTop: '10px' }}>
        <strong>Status:</strong> {status.level}
        {status.text ? ` — ${status.text}` : ''}
      </p>

      {message && <p style={{ color: 'green', fontWeight: 'bold' }}>{message}</p>}
    </div>
  );
}

export default App;
