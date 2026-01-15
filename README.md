
# discordRPC

A Discord Rich Presence application that displays your current reading activity from Goodreads and StoryGraph.

## Features

- Display current book from Goodreads
- Display current book from StoryGraph
- Real-time Discord Rich Presence updates
- Automatic synchronization

## Installation

### From Release

1. Download the latest release from the [Releases](https://github.com/Frosty63101/discordRPC/releases) page
2. Extract the archive
3. Run the executable
4. Configure your credentials (see [Configuration](#configuration))

### From Source

1. Clone the repository:
    ```bash
    git clone https://github.com/Frosty63101/discordRPC.git
    cd discordRPC
    ```

2. Install dependencies:
    ```bash
    npm install
    ```

3. Build the project:
    ```bash
    npm run build
    ```

4. Start the application:
    ```bash
    npm start
    ```

## Configuration

### Goodreads ID

1. Visit [Goodreads.com](https://www.goodreads.com)
2. Go to your profile
3. Your ID is in the URL: `goodreads.com/user/show/**YOUR_ID**`

### StoryGraph Remember Cookie

1. Log in to [StoryGraph](https://www.storygraph.com)
2. Open Browser DevTools (F12)
3. Go to Application → Cookies
4. Find the `remember` cookie and copy its value
5. Paste it into the application settings

## Requirements

- Node.js 14+
- Discord installed and running
- Active Goodreads or StoryGraph account

## License

MIT
