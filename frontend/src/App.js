import { useCallback, useEffect, useRef, useState } from 'react';
import './App.css';

const apiBaseUrl = 'http://127.0.0.1:5000';
const platformLabels = {
  goodreads: 'Goodreads',
  storygraph: 'StoryGraph',
  audiobookshelf: 'Audiobookshelf',
};

async function apiRequest(path, options = {}) {
  let response;
  try {
    response = await fetch(apiBaseUrl + path, options);
  } catch {
    throw new Error('Cannot contact the local service. Restart the desktop application.');
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || 'Request failed (HTTP ' + response.status + ')');
  return data;
}

function logLevel(line) {
  if (/\b(ERROR|CRITICAL)\b/i.test(line)) return 'error';
  if (/\bWARNING\b/i.test(line)) return 'warning';
  return 'info';
}

function Toggle({ id, label, description, checked, onChange, disabled = false }) {
  return (
    <label className="setting-toggle" htmlFor={id}>
      <span>
        <strong>{label}</strong>
        <span className="setting-help">{description}</span>
      </span>
      <input
        id={id}
        type="checkbox"
        className="switch-input"
        checked={Boolean(checked)}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="switch-appearance" aria-hidden="true" />
    </label>
  );
}

function App() {
  const [config, setConfig] = useState(null);
  const [savedConfig, setSavedConfig] = useState(null);
  const [books, setBooks] = useState({});
  const [selectedBook, setSelectedBook] = useState('');
  const [health, setHealth] = useState(null);
  const [logs, setLogs] = useState([]);
  const [followLogs, setFollowLogs] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [bookCoverFailed, setBookCoverFailed] = useState(false);

  const mountedRef = useRef(false);
  const logPaneRef = useRef(null);
  const followRef = useRef(true);
  const refreshBusyRef = useRef(false);
  const messageTimerRef = useRef(null);

  const showNotice = useCallback((type, text) => {
    setNotice({ type, text });
    clearTimeout(messageTimerRef.current);
    messageTimerRef.current = setTimeout(() => setNotice(null), 6500);
  }, []);

  const fetchHealth = useCallback(async () => {
    try {
      setHealth(await apiRequest('/api/health'));
    } catch {
      setHealth(null);
    }
  }, []);

  const fetchLogs = useCallback(async () => {
    try {
      const data = await apiRequest('/api/logs?limit=50');
      setLogs(Array.isArray(data.lines) ? data.lines.slice(-50) : []);
    } catch {
      // Leave previously loaded lines visible during transient outages.
    }
  }, []);

  const fetchBooks = useCallback(async () => {
    if (refreshBusyRef.current) return;
    refreshBusyRef.current = true;
    try {
      const data = await apiRequest('/api/scraper/get_books');
      if (!Array.isArray(data)) throw new Error('Unexpected books response');
      setBooks(data[0] || {});
      setSelectedBook(data[1] || '');
      return data;
    } catch (error) {
      setBooks({});
      setSelectedBook('');
      throw error;
    } finally {
      refreshBusyRef.current = false;
    }
  }, []);

  const saveSettings = useCallback(async (nextConfig) => {
    const previous = savedConfig;
    const preferenceKeys = ['minimizeToTray', 'minimizeOnMinimize', 'startOnStartup'];
    const prefs = Object.fromEntries(preferenceKeys.map((key) => [key, Boolean(nextConfig[key])]));
    const oldPrefs = Object.fromEntries(preferenceKeys.map((key) => [key, Boolean(previous?.[key])]));
    let applied = false;
    try {
      if (window.electron?.setPreferences) {
        await window.electron.setPreferences(prefs);
        applied = true;
      } else if (nextConfig.startOnStartup !== previous?.startOnStartup) {
        throw new Error('Launch at login requires the packaged desktop application.');
      }
      await apiRequest('/api/config/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(nextConfig),
      });
      const fresh = await apiRequest('/api/config');
      setConfig(fresh);
      setSavedConfig(fresh);
      showNotice('success', 'Settings saved.');
      return true;
    } catch (error) {
      if (applied && window.electron?.setPreferences) {
        await window.electron.setPreferences(oldPrefs).catch(() => {});
      }
      showNotice('error', error.message);
      return false;
    }
  }, [savedConfig, showNotice]);

  const handlePreferenceChange = useCallback(async (key, value) => {
    const nextConfig = { ...config, [key]: value };
    setConfig(nextConfig);
    setBusy(true);
    try {
      const okay = await saveSettings(nextConfig);
      if (!okay) setConfig(config);
    } finally {
      setBusy(false);
    }
  }, [config, saveSettings]);

  const handleSave = useCallback(async () => {
    if (!config) return false;
    setBusy(true);
    try {
      return await saveSettings(config);
    } finally {
      setBusy(false);
    }
  }, [config, saveSettings]);

  const handlePlatformChange = useCallback(async (platform) => {
    if (!config) return;
    const nextConfig = { ...config, platform, current_isbn: null };
    setConfig(nextConfig);
    setBooks({});
    setSelectedBook('');
    setBusy(true);
    try {
      if (await saveSettings(nextConfig)) {
        await apiRequest('/api/scraper/refresh', { method: 'POST' });
        await fetchBooks();
      }
    } catch (error) {
      showNotice('error', error.message);
    } finally {
      setBusy(false);
    }
  }, [config, fetchBooks, saveSettings, showNotice]);

  const handleRefresh = useCallback(async () => {
    setBusy(true);
    try {
      await apiRequest('/api/scraper/refresh', { method: 'POST' });
      const data = await fetchBooks();
      showNotice('success', 'Found ' + Object.keys(data[0] || {}).length + ' book(s).');
    } catch (error) {
      showNotice('error', error.message);
    } finally {
      setBusy(false);
      fetchLogs();
    }
  }, [fetchBooks, fetchLogs, showNotice]);

  const handleBookChange = useCallback(async (value) => {
    if (!value) return;
    setSelectedBook(value);
    try {
      await apiRequest('/api/book/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ isbn: value }),
      });
      setConfig((prev) => ({ ...prev, current_isbn: value }));
      setSavedConfig((prev) => ({ ...prev, current_isbn: value }));
      showNotice('success', 'Selected book updated.');
    } catch (error) {
      showNotice('error', error.message);
    }
  }, [showNotice]);

  const handlePresence = useCallback(async (action) => {
    setBusy(true);
    try {
      if (action === 'start' && JSON.stringify(config) !== JSON.stringify(savedConfig)) {
        const saved = await saveSettings(config);
        if (!saved) return;
      }
      const result = await apiRequest('/api/presence/' + action, { method: 'POST' });
      showNotice('success', result.message || 'Discord presence updated.');
      await fetchHealth();
    } catch (error) {
      showNotice('error', error.message);
    } finally {
      setBusy(false);
      fetchLogs();
    }
  }, [config, savedConfig, saveSettings, fetchHealth, fetchLogs, showNotice]);

  const testDiscord = useCallback(async () => {
    setBusy(true);
    try {
      await apiRequest('/api/presence/test', { method: 'POST' });
      showNotice('success', 'Discord RPC connection succeeded.');
    } catch (error) {
      showNotice('error', error.message);
    } finally {
      setBusy(false);
      fetchLogs();
    }
  }, [showNotice, fetchLogs]);

  useEffect(() => {
    if (mountedRef.current) return;
    mountedRef.current = true;
    let cancelled = false;

    const initialize = async () => {
      try {
        const fresh = await apiRequest('/api/config');
        if (cancelled) return;
        setConfig(fresh);
        setSavedConfig(fresh);
        try {
          await fetchBooks();
        } catch (error) {
          if (!cancelled) showNotice('warning', error.message);
        }
        if (fresh.startByDefault && !cancelled) {
          await apiRequest('/api/presence/start', { method: 'POST' }).catch((error) => {
            if (!cancelled) showNotice('error', error.message);
          });
        }
      } catch (error) {
        if (!cancelled) showNotice('error', error.message);
      }
      if (!cancelled) {
        fetchHealth();
        fetchLogs();
      }
    };
    initialize();
    const polling = setInterval(() => {
      fetchHealth();
      fetchLogs();
    }, 5000);
    return () => {
      cancelled = true;
      clearInterval(polling);
      clearTimeout(messageTimerRef.current);
      mountedRef.current = false;
    };
  }, [fetchBooks, fetchHealth, fetchLogs, showNotice]);

  useEffect(() => {
    if (followRef.current && logPaneRef.current) {
      logPaneRef.current.scrollTop = logPaneRef.current.scrollHeight;
    }
  }, [logs]);

  const updateField = (key, value) => setConfig((previous) => ({ ...previous, [key]: value }));
  const theme = config?.theme || 'system';
  const platform = config?.platform || 'goodreads';
  const activeBook = books[selectedBook] || null;
  const isActive = Boolean(health?.presenceRunning);
  const hasUnsavedSettings = Boolean(config && savedConfig && JSON.stringify(config) !== JSON.stringify(savedConfig));

  if (!config) {
    return (
      <div className="app-shell" data-theme="system">
        <div className="loading-card">Connecting to Reading Presence…</div>
      </div>
    );
  }

  return (
    <div className="app-shell" data-theme={theme}>
      <div className="app-container">
        <header className="topbar">
          <div className="brand">
            <img className="brand-icon" src="./book-icon.svg" alt="" />
            <div>
              <div className="eyebrow">DISCORD RICH PRESENCE</div>
              <h1>Reading Presence</h1>
              <p className="subtext">Your books and listening activity, on Discord.</p>
            </div>
          </div>
          <div className="header-controls">
            <label className="theme-control">
              <span>Appearance</span>
              <select aria-label="Appearance" value={theme} onChange={(event) => handlePreferenceChange('theme', event.target.value)} disabled={busy}>
                <option value="system">System</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </select>
            </label>
            <div className={'connection-pill ' + (isActive ? 'online' : 'offline')} role="status">
              <span className="status-dot" />
              {isActive ? 'Connected to Discord' : health?.presenceRequested ? 'Connecting' : 'Not running'}
            </div>
          </div>
        </header>

        {notice && <div role="alert" className={'notice ' + notice.type}>{notice.text}</div>}

        <section className="overview panel">
          <div className="overview-copy">
            <div className="eyebrow">NOW SELECTED</div>
            <h2>{activeBook?.title || 'Choose a book to get started'}</h2>
            <p>{activeBook ? 'by ' + (activeBook.author || 'Unknown Author') : 'Connect one of your reading platforms and refresh your library.'}</p>
            <span className="source-chip">{platformLabels[platform] || platform}</span>
          </div>
          <div className="book-preview" aria-label="Book cover preview">
            {activeBook?.coverArt && !bookCoverFailed ? (
              <img
                src={activeBook.coverArt}
                alt={'Cover for ' + (activeBook.title || 'book')}
                onError={() => setBookCoverFailed(true)}
                onLoad={() => setBookCoverFailed(false)}
              />
            ) : (
              <img src="./book-icon.svg" alt="Open book illustration" />
            )}
          </div>
          <div className="overview-actions">
            <button type="button" className="button primary" disabled={busy || isActive} onClick={() => handlePresence('start')}>Start presence</button>
            <button type="button" className="button secondary" disabled={busy || !isActive} onClick={() => handlePresence('stop')}>Stop presence</button>
          </div>
        </section>

        <div className="columns">
          <section className="panel form-panel">
            <div className="section-heading">
              <div>
                <h2>Reading source</h2>
                <p>Choose where to get your current books.</p>
              </div>
            </div>
            <div className="form-grid">
              <label className="field full">
                <span>Book platform</span>
                <select value={platform} disabled={busy} onChange={(event) => handlePlatformChange(event.target.value)}>
                  <option value="goodreads">Goodreads</option>
                  <option value="storygraph">StoryGraph</option>
                  <option value="audiobookshelf">Audiobookshelf</option>
                </select>
              </label>

              {platform === 'goodreads' && (
                <label className="field full">
                  <span>Goodreads user ID</span>
                  <input value={config.goodreads_id || ''} onChange={(event) => updateField('goodreads_id', event.target.value)} placeholder="Your numerical user ID" />
                </label>
              )}

              {platform === 'storygraph' && (
                <>
                  <label className="field full">
                    <span>StoryGraph username</span>
                    <input value={config.storygraph_username || ''} onChange={(event) => updateField('storygraph_username', event.target.value)} placeholder="Your username" />
                  </label>
                  <label className="field full">
                    <span>StoryGraph remember_user_token</span>
                    <input type="password" autoComplete="off" value={config.storygraph_remember_user_token || ''} onChange={(event) => updateField('storygraph_remember_user_token', event.target.value)} placeholder="Login cookie value" />
                  </label>
                </>
              )}

              {platform === 'audiobookshelf' && (
                <>
                  <label className="field full">
                    <span>Server URL</span>
                    <input value={config.audiobookshelf_url || ''} onChange={(event) => updateField('audiobookshelf_url', event.target.value)} placeholder="https://books.example.com" />
                  </label>
                  <label className="field full">
                    <span>API key</span>
                    <input type="password" autoComplete="off" value={config.audiobookshelf_api_key || ''} onChange={(event) => updateField('audiobookshelf_api_key', event.target.value)} placeholder="Leave blank to keep saved key" />
                    <small>The saved token is not shown again.</small>
                  </label>
                  <label className="field full">
                    <span>User UUID</span>
                    <input value={config.audiobookshelf_user_id || ''} onChange={(event) => updateField('audiobookshelf_user_id', event.target.value)} placeholder="User ID from Audiobookshelf" />
                  </label>
                </>
              )}

              <label className="field full">
                <span>Currently reading</span>
                <select
                  value={selectedBook}
                  disabled={busy || !Object.keys(books).length}
                  onChange={(event) => { setBookCoverFailed(false); handleBookChange(event.target.value); }}
                >
                  <option value="">No book selected</option>
                  {Object.entries(books).map(([key, book]) => (
                    <option key={key} value={key}>{book.title} — {book.author}</option>
                  ))}
                </select>
                <small>{platform === 'audiobookshelf' ? 'Discord follows detected active listening automatically.' : 'Select the book to display on Discord.'}</small>
              </label>
            </div>
            <div className="panel-actions">
              <button type="button" className="button secondary" disabled={busy} onClick={handleRefresh}>Refresh books</button>
              <button type="button" className="button primary" disabled={busy || !hasUnsavedSettings} onClick={handleSave}>Save settings{hasUnsavedSettings ? ' *' : ''}</button>
            </div>
          </section>

          <section className="panel settings-panel">
            <div className="section-heading">
              <div>
                <h2>Discord &amp; app settings</h2>
                <p>Control your activity and desktop behavior.</p>
              </div>
            </div>
            <div className="form-grid">
              <label className="field full">
                <span>Discord application ID</span>
                <input inputMode="numeric" value={config.discord_app_id || ''} onChange={(event) => updateField('discord_app_id', event.target.value)} placeholder="Discord application ID" />
                <small>Use the Application ID from the Discord Developer Portal—not a bot token.</small>
              </label>
              <label className="field full">
                <span>Sync interval (seconds)</span>
                <input type="number" min="5" max="600" step="1" value={config.update_interval ?? 60} onChange={(event) => updateField('update_interval', Number(event.target.value) || 5)} />
              </label>
            </div>
            <div className="settings-list">
              <Toggle id="close-to-tray" label="Close to system tray" description="Closing the window keeps the app running in the tray." disabled={busy} checked={config.minimizeToTray} onChange={(checked) => handlePreferenceChange('minimizeToTray', checked)} />
              <Toggle id="minimize-to-tray" label="Minimize to system tray" description="The minimize button hides the window instead of showing it in the taskbar." disabled={busy} checked={config.minimizeOnMinimize} onChange={(checked) => handlePreferenceChange('minimizeOnMinimize', checked)} />
              <Toggle id="start-on-login" label="Launch at login" description="Start the desktop application when you sign in to your computer." disabled={busy} checked={config.startOnStartup} onChange={(checked) => handlePreferenceChange('startOnStartup', checked)} />
              <Toggle id="start-presence" label="Start presence automatically" description="Connect to Discord when the desktop app opens." disabled={busy} checked={config.startByDefault} onChange={(checked) => handlePreferenceChange('startByDefault', checked)} />
            </div>
            <div className="panel-actions">
              <button type="button" className="button secondary" disabled={busy} onClick={testDiscord}>Test Discord connection</button>
              <button type="button" className="button ghost danger" onClick={() => window.electron?.quit?.()}>Quit app</button>
            </div>
          </section>
        </div>

        <section className="panel log-panel">
          <div className="log-header">
            <div>
              <h2>Activity logs</h2>
              <p>Last 50 lines from the app's log file. Updates every 5 seconds.</p>
            </div>
            <div className="log-controls">
              <label className="checkbox-line">
                <input type="checkbox" checked={followLogs} onChange={(event) => { followRef.current = event.target.checked; setFollowLogs(event.target.checked); }} />
                Follow newest
              </label>
              <button type="button" className="button small secondary" onClick={fetchLogs}>Refresh logs</button>
            </div>
          </div>
          <div className="log-scroll" ref={logPaneRef} role="log" aria-label="Activity logs" aria-live="off">
            {logs.length ? logs.map((line, index) => (
              <div className={'log-line ' + logLevel(line)} key={index}>{line || '\u00a0'}</div>
            )) : (
              <div className="log-empty">No logs yet. Activity and errors will show up here.</div>
            )}
          </div>
        </section>

        <footer className="footer">Reading Presence <span>•</span> Goodreads, StoryGraph &amp; Audiobookshelf <span>•</span> Runs on Windows, macOS &amp; Linux</footer>
      </div>
    </div>
  );
}

export default App;
