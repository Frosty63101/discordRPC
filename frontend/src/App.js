import { useEffect, useState, useRef, useCallback } from 'react';
import './App.css';

const apiBaseUrl = 'http://localhost:5000';

function App() {
    const [config, setConfig] = useState(null);
    const [books, setBooks] = useState({});
    const [selectedISBN, setSelectedISBN] = useState('');
    const [status, setStatus] = useState('');
    const [message, setMessage] = useState('');

    const intervalRef = useRef(null);
    const messageTimer = useRef(null);

    const showMessage = (msg) => {
        setMessage(msg);
        clearTimeout(messageTimer.current);
        messageTimer.current = setTimeout(() => setMessage(''), 2500);
    };

    const fetchStatus = useCallback(() => {
        fetch(`${apiBaseUrl}/api/status`)
            .then(res => res.json())
            .then(data => {
                const newStatus = Array.isArray(data.status) ? data.status.join(', ') : data.status;
                setStatus(newStatus || '');
            })
            .catch(() => {});
    }, []);

    const fetchConfig = useCallback(() => {
        return fetch(`${apiBaseUrl}/api/config`)
            .then(res => res.json())
            .then(cfg => {
                setConfig(cfg);
                return cfg;
            })
            .catch(() => null);
    }, []);

    const fetchBooks = useCallback(() => {
        return fetch(`${apiBaseUrl}/api/scraper/get_books`)
            .then(res => res.json())
            .then(([bookData, current]) => {
                setBooks(bookData || {});
                setSelectedISBN(current || '');
                return { bookData, current };
            })
            .catch(() => null);
    }, []);

    const saveConfig = useCallback((nextConfig) => {
        const cfgToSave = nextConfig ?? config;
        if (!cfgToSave) return Promise.resolve(false);

        return fetch(`${apiBaseUrl}/api/config/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(cfgToSave),
        })
            .then(() => {
                showMessage('✅ Config saved');
                return true;
            })
            .then(() => fetchStatus())
            .catch(() => false);
    }, [config, fetchStatus]);

    const updateBook = useCallback((isbn) => {
        setSelectedISBN(isbn);
        return fetch(`${apiBaseUrl}/api/book/select`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ isbn }),
        })
            .then(res => {
                if (!res.ok) throw new Error('Book select failed');
                showMessage('✅ Book updated');
            })
            .then(() => fetchStatus())
            .catch(() => {});
    }, [fetchStatus]);

    const handlePlatformChange = useCallback((newPlatform) => {
        if (!config) return;

        // Update local config immediately
        const updated = { ...config, platform: newPlatform, current_isbn: null };
        setConfig(updated);

        // Save, then re-scrape books for the new platform
        saveConfig(updated)
            .then(() => fetchBooks())
            .then(() => showMessage(`✅ Switched to ${newPlatform}`))
            .then(() => fetchStatus())
            .catch(() => {});
    }, [config, saveConfig, fetchBooks, fetchStatus]);

    const startPresence = () => {
        fetch(`${apiBaseUrl}/api/presence/start`, { method: 'POST' })
            .then(res => {
                if (!res.ok) throw new Error('start failed');
                showMessage('✅ Presence started');
            })
            .then(() => fetchStatus())
            .catch(() => {});
    };

    const stopPresence = () => {
        fetch(`${apiBaseUrl}/api/presence/stop`, { method: 'POST' })
            .then(res => {
                if (!res.ok) throw new Error('stop failed');
                showMessage('🛑 Presence stopped');
            })
            .then(() => fetchStatus())
            .catch(() => {});
    };

    const exit = () => {
        const controller = new AbortController();
        const t = setTimeout(() => controller.abort(), 800);

        fetch(`${apiBaseUrl}/shutdown`, { method: 'POST', signal: controller.signal })
            .catch(() => {})
            .finally(() => clearTimeout(t));

        showMessage('🛑 Exiting...');
        window.electron?.ipcRenderer?.send('force-quit');
    };

    useEffect(() => {
        if (window.__GOODREADS_RPC_INITIALIZED__) return;
        window.__GOODREADS_RPC_INITIALIZED__ = true;

        fetchConfig()
            .then(() => fetchBooks())
            .catch(() => {});

        fetch(`${apiBaseUrl}/api/getStartByDefault`)
            .then(res => res.json())
            .then(data => {
                if (data.startByDefault) {
                    fetch(`${apiBaseUrl}/api/presence/start`, { method: 'POST' })
                        .then(() => showMessage('✅ Presence started by default'))
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
    }, [fetchStatus, fetchConfig, fetchBooks]);

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
                onChange={e => handlePlatformChange(e.target.value)}
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
                        onBlur={() => {
                            saveConfig();
                            fetchBooks();
                            fetchStatus();
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
                        onChange={e => setConfig({ ...config, storygraph_username: e.target.value })}
                        onBlur={() => {
                            saveConfig();
                            fetchBooks();
                            fetchStatus();
                        }}
                    />
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
                    const next = e.target.value;
                    updateBook(next);
                    // Also refresh local config's current_isbn so the UI and backend stay aligned
                    const updated = { ...config, current_isbn: next };
                    setConfig(updated);
                    saveConfig(updated);
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
                        onChange={e => setConfig({ ...config, minimizeToTray: e.target.checked })}
                        onBlur={() => { saveConfig(); fetchStatus(); }}
                    />
                    {' '}Minimize to Tray
                </label>
            </div>

            <div>
                <label>
                    <input
                        type="checkbox"
                        checked={!!config.startOnStartup}
                        onChange={e => setConfig({ ...config, startOnStartup: e.target.checked })}
                        onBlur={() => {
                            saveConfig();
                            fetch(`${apiBaseUrl}/api/startup/enable`, { method: 'POST' }).catch(() => {});
                            fetchStatus();
                        }}
                    />
                    {' '}Start on Startup
                </label>
            </div>

            <div style={{ display: 'flex', gap: '10px', marginTop: '20px' }}>
                <button className="btn" onClick={() => saveConfig()}>Save Config</button>
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
