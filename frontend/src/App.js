import { useEffect, useState, useRef } from 'react';
import './App.css';

function App() {
    const [config, setConfig] = useState(null);
    const [books, setBooks] = useState({});
    const [selectedISBN, setSelectedISBN] = useState('');
    const [status, setStatus] = useState('');
    const [message, setMessage] = useState('');
    const intervalRef = useRef(null);
    const messageTimer = useRef(null);

    useEffect(() => {
        if (window.__GOODREADS_RPC_INITIALIZED__) return;
        window.__GOODREADS_RPC_INITIALIZED__ = true;

        // Load config
        safeFetchJSON('http://localhost:5000/api/config').then((cfg) => {
            if (cfg) setConfig(cfg);
        });

        // startByDefault
        safeFetchJSON('http://localhost:5000/api/getStartByDefault').then((data) => {
            if (data?.startByDefault) {
                fetch('http://localhost:5000/api/presence/start', { method: 'POST' })
                    .then(() => showMessage('Presence started by default'))
                    .catch(() => {});
            }
        });

        // books
        safeFetchJSON('http://localhost:5000/api/scraper/get_books').then((two) => {
            if (two && Array.isArray(two) && two.length === 2) {
                const [bookData, current] = two;
                setBooks(bookData || {});
                setSelectedISBN(current || '');
            }
        });

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
    }, []);

    async function safeFetchJSON(url, init) {
        try {
            const res = await fetch(url, init);
            if (!res.ok) return null;
            return await res.json();
        } catch {
            return null;
        }
    }

    const fetchStatus = async () => {
        const data = await safeFetchJSON('http://localhost:5000/api/status');
        if (!data) return;
        const newStatus = Array.isArray(data.status) ? data.status.filter(Boolean).join(', ') : data.status;
        setStatus(newStatus || '');
    };

    const showMessage = (msg) => {
        setMessage(msg);
        clearTimeout(messageTimer.current);
        messageTimer.current = setTimeout(() => setMessage(''), 2500);
    };

    const saveConfig = () => {
        if (!config) return;
        fetch('http://localhost:5000/api/config/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config),
        }).then(() => {
            showMessage('Config saved');
            fetchStatus();
        }).catch(() => {});
    };

    const updateBook = (isbn) => {
        setSelectedISBN(isbn);
        fetch('http://localhost:5000/api/book/select', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ isbn }),
        }).then(() => {
            showMessage('Book updated');
            fetchStatus();
        }).catch(() => {});
    };

    const startPresence = () => {
        fetch('http://localhost:5000/api/presence/start', { method: 'POST' })
            .then(() => { showMessage('Presence started'); fetchStatus(); })
            .catch(() => {});
    };

    const stopPresence = () => {
        fetch('http://localhost:5000/api/presence/stop', { method: 'POST' })
            .then(() => { showMessage('Presence stopped'); fetchStatus(); })
            .catch(() => {});
    };

    const exit = async () => {
        try {
            await fetch('http://localhost:5000/shutdown', { method: 'POST' });
        } catch {}
        showMessage('Exiting…');
        setTimeout(() => {
            window.electron?.ipcRenderer?.send('force-quit');
        }, 500);
    };

    if (!config) return <div style={{ padding: '20px' }}>Loading configuration...</div>;

    return (
        <div style={{
            padding: '24px',
            maxWidth: '640px',
            margin: '0 auto',
            fontFamily: 'Segoe UI, sans-serif',
            color: '#333',
        }}>
            <h1 style={{ marginBottom: '20px', color: '#444' }}>Goodreads Discord RPC</h1>

            <label>Discord App ID:</label>
            <input
                className="input"
                value={config.discord_app_id || ''}
                onChange={e => setConfig({ ...config, discord_app_id: e.target.value })}
                onBlur={saveConfig}
            />

            <label>Goodreads User ID:</label>
            <input
                className="input"
                value={config.goodreads_id || ''}
                onChange={e => setConfig({ ...config, goodreads_id: e.target.value })}
                onBlur={saveConfig}
            />

            <label>Update Interval (seconds):</label>
            <input
                type="number"
                className="input"
                value={config.update_interval ?? 60}
                onChange={e => setConfig({ ...config, update_interval: parseInt(e.target.value || '60', 10) })}
                onBlur={saveConfig}
            />

            <label>Currently Reading:</label>
            <select
                className="input"
                value={selectedISBN}
                onChange={e => {
                    updateBook(e.target.value);
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
                        fetch('http://localhost:5000/api/config/save', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(updated),
                        }).finally(fetchStatus);
                    }}
                /> {' '}Minimize to Tray
            </label>

            <label>
                <input
                    type="checkbox"
                    checked={!!config.startOnStartup}
                    onChange={e => {
                        const updated = { ...config, startOnStartup: e.target.checked };
                        setConfig(updated);
                        fetch('http://localhost:5000/api/config/save', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(updated),
                        }).then(() => {
                            fetch('http://localhost:5000/api/startup/enable', { method: 'POST' }).catch(() => {});
                            fetchStatus();
                        });
                    }}
                /> {' '}Start on Startup
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
