import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App';

let savedConfig;

beforeEach(() => {
  savedConfig = {
    platform: 'goodreads',
    goodreads_id: '1234',
    discord_app_id: '123456789012345678',
    update_interval: 60,
    minimizeToTray: true,
    minimizeOnMinimize: false,
    startOnStartup: false,
    startByDefault: false,
    theme: 'system',
    current_isbn: null,
  };

  window.electron = {
    setPreferences: jest.fn(async (preferences) => preferences),
    quit: jest.fn(),
  };

  global.fetch = jest.fn(async (url, options = {}) => {
    let data;
    if (url.endsWith('/api/config/save')) {
      savedConfig = { ...savedConfig, ...JSON.parse(options.body) };
      data = { message: 'Settings saved' };
    } else if (url.endsWith('/api/config')) {
      data = { ...savedConfig };
    } else if (url.endsWith('/api/scraper/get_books')) {
      data = [{
        'gr-1': {
          isbn: 'gr-1',
          title: 'A Test Book',
          author: 'Example Writer',
          platform: 'goodreads',
        },
      }, 'gr-1'];
    } else if (url.endsWith('/api/health')) {
      data = { ok: true, presenceRunning: false, presenceRequested: false };
    } else if (url.includes('/api/logs')) {
      data = {
        lines: Array.from(
          { length: 70 },
          (_, index) => '2026-10-19 00:00:00 - INFO - log line ' + (index + 1)
        ),
      };
    } else {
      data = { message: 'OK' };
    }
    return { ok: true, json: async () => data };
  });
});

afterEach(() => {
  delete window.electron;
  jest.clearAllMocks();
});

test('shows the responsive dashboard and selected book', async () => {
  render(<App />);
  expect(await screen.findByRole('heading', { name: 'Reading Presence' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'A Test Book' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Reading source' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Discord & app settings' })).toBeInTheDocument();
});

test('activity log is scrollable and contains no more than 50 lines', async () => {
  render(<App />);
  const log = await screen.findByRole('log');
  await waitFor(() => {
    expect(log.querySelectorAll('.log-line')).toHaveLength(50);
  });
  expect(log.textContent).toContain('log line 70');
  expect(log.textContent).not.toContain('log line 1\n');
});

test('theme selector persists dark appearance', async () => {
  const { container } = render(<App />);
  const themeSelector = await screen.findByLabelText('Appearance');
  fireEvent.change(themeSelector, { target: { value: 'dark' } });

  await waitFor(() => {
    expect(savedConfig.theme).toBe('dark');
    expect(container.querySelector('.app-shell')).toHaveAttribute('data-theme', 'dark');
  });
});

test('close-to-tray switch immediately updates Electron settings', async () => {
  render(<App />);
  const toggle = await screen.findByRole('checkbox', { name: /Close to system tray/i });
  fireEvent.click(toggle);
  await waitFor(() => {
    expect(window.electron.setPreferences).toHaveBeenCalledWith(
      expect.objectContaining({
        minimizeToTray: false,
        minimizeOnMinimize: false,
        startOnStartup: false,
      })
    );
    expect(savedConfig.minimizeToTray).toBe(false);
  });
});
