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
                const newStatus = Array.isArray(data.status)
                    ? data.status.join(', ')
                    : data.status;
                setStatus(newStatus || '');
            })
            .catch(() => {
            });
    }, []); 

    useEffect(() => {
        if (window.__GOODREADS_RPC_INITIALIZED__) return;
        window.__GOODREADS_RPC_INITIALIZED__ = true;

        // Load config
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

        fetch('http://localhost:5000/api/scraper/get_books')
            .then(res => res.json())
            .then(([bookData, current]) => {
                setBooks(bookData || {});
                setSelectedISBN(current || '');
            })
            .catch(() => {});

        // status polling (not in background)
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
    }, [fetchStatus]);

    const showMessage = msg => {
        setMessage(msg);
        clearTimeout(messageTimer.current);
        messageTimer.current = setTimeout(() => setMessage(''), 3000);
    };

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

    const updateBook = isbn => {
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
        fetch('http://localhost:5000/shutdown', { method: 'POST' })
            .catch(() => {})
            .finally(() => {
                showMessage('🛑 Exiting...');
                setTimeout(() => {
                    window.electron?.ipcRenderer?.send('force-quit');
                }, 2000);
            });
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
                value={config.discord_app_id || ''}
                onChange={e => {
                    setConfig({ ...config, discord_app_id: e.target.value });
                    saveConfig();
                    fetchStatus();
                }}
            />

            <label>Goodreads User ID:</label>
            <input
                className="input"
                value={config.goodreads_id || ''}
                onChange={e => {
                    setConfig({ ...config, goodreads_id: e.target.value });
                    saveConfig();
                    fetchStatus();
                }}
            />

            <label>Update Interval (seconds):</label>
            <input
                type="number"
                className="input"
                value={config.update_interval ?? 60}
                onChange={e => {
                    const val = parseInt(e.target.value, 10);
                    setConfig({ ...config, update_interval: Number.isNaN(val) ? 60 : val });
                    saveConfig();
                    fetchStatus();
                }}
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
                    checked={!!config.minimizeToTray}
                    onChange={e => {
                        const updated = { ...config, minimizeToTray: e.target.checked };
                        setConfig(updated);
                        saveConfig();
                        fetchStatus();
                    }}
                />
                {' '}Minimize to Tray
            </label>

            <label>
                <input
                    type="checkbox"
                    checked={!!config.startOnStartup}
                    onChange={e => {
                        const updated = { ...config, startOnStartup: e.target.checked };
                        setConfig(updated);
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
            {message && (
                <p style={{ color: 'green', fontWeight: 'bold' }}>{message}</p>
            )}
        </div>
    );
}

export default App;
