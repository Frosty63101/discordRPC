// App.js
import { useEffect, useState } from 'react';

function App() {
  const [config, setConfig] = useState(null);
  const [books, setBooks] = useState({});
  const [selectedISBN, setSelectedISBN] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    fetch("http://localhost:5000/api/config")
      .then(res => res.json())
      .then(data => setConfig(data));

    fetch("http://localhost:5000/api/scraper/get_books")
      .then(res => res.json())
      .then(([bookData, current]) => {
        setBooks(bookData);
        setSelectedISBN(current);
      });

    fetch("http://localhost:5000/api/status")
      .then(res => res.json())
      .then(data => setStatus(data.status));
  }, []);

  const saveConfig = () => {
    fetch("http://localhost:5000/api/config/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });
  };

  const updateBook = (isbn) => {
    setSelectedISBN(isbn);
    fetch("http://localhost:5000/api/book/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ isbn }),
    });
  };

  const startPresence = () => {
    fetch("http://localhost:5000/api/presence/start", { method: "POST" });
  };

  const stopPresence = () => {
    fetch("http://localhost:5000/api/presence/stop", { method: "POST" });
  };

  if (!config) return <div>Loading configuration...</div>;

  return (
    <div style={{ padding: "20px", fontFamily: "sans-serif" }}>
      <h1>Goodreads Discord RPC</h1>

      <div>
        <label>Discord App ID:</label>
        <input
          value={config.discord_app_id}
          onChange={(e) => setConfig({ ...config, discord_app_id: e.target.value })}
        />
      </div>

      <div>
        <label>Goodreads User ID:</label>
        <input
          value={config.goodreads_id}
          onChange={(e) => setConfig({ ...config, goodreads_id: e.target.value })}
        />
      </div>

      <div>
        <label>Update Interval (seconds):</label>
        <input
          type="number"
          value={config.update_interval}
          onChange={(e) =>
            setConfig({ ...config, update_interval: parseInt(e.target.value) })
          }
        />
      </div>

      <div>
        <label>Currently Reading:</label>
        <select
          value={selectedISBN}
          onChange={(e) => updateBook(e.target.value)}
        >
          {Object.entries(books).map(([isbn, book]) => (
            <option key={isbn} value={isbn}>
              {book.title} by {book.author}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label>
          <input
            type="checkbox"
            checked={config.minimizeToTray}
            onChange={(e) =>
              setConfig({ ...config, minimizeToTray: e.target.checked })
            }
          />
          Minimize to Tray
        </label>
      </div>

      <div>
        <label>
          <input
            type="checkbox"
            checked={config.startOnStartup}
            onChange={(e) =>
              setConfig({ ...config, startOnStartup: e.target.checked })
            }
          />
          Start on Startup
        </label>
      </div>

      <div style={{ marginTop: "20px" }}>
        <button onClick={saveConfig}>Save Config</button>
        <button onClick={startPresence}>Start Presence</button>
        <button onClick={stopPresence}>Stop Presence</button>
      </div>

      <p>Status: {Array.isArray(status) ? status.join(', ') : status}</p>
    </div>
  );
}

export default App;
