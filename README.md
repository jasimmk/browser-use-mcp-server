# browser-use-mcp-server

<div align="center">

[![Twitter URL](https://img.shields.io/twitter/url/https/twitter.com/cobrowser.svg?style=social&label=Follow%20%40cobrowser)](https://x.com/cobrowser)
[![Discord](https://img.shields.io/discord/1351569878116470928?logo=discord&logoColor=white&label=discord&color=white)](https://discord.gg/gw9UpFUhyY)
[![PyPI version](https://badge.fury.io/py/browser-use-mcp-server.svg)](https://badge.fury.io/py/browser-use-mcp-server)

**An MCP server that enables AI agents to control web browsers using
[browser-use](https://github.com/browser-use/browser-use).**

> **🔗 Managing multiple MCP servers?** Simplify your development workflow with [agent-browser](https://github.com/co-browser/agent-browser)

</div>

## Prerequisites

- [uv](https://github.com/astral-sh/uv) - Fast Python package manager
- [Playwright](https://playwright.dev/) - Browser automation
- [mcp-proxy](https://github.com/sparfenyuk/mcp-proxy) - Required for stdio mode

```bash
# Install prerequisites
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install mcp-proxy
uv tool update-shell
```

## Environment

Create a `.env` file:

```bash
# OpenAI (default provider)
OPENAI_API_KEY=your-openai-api-key

# Anthropic (alternative provider)
ANTHROPIC_API_KEY=your-anthropic-api-key

# Ollama (local provider)
OLLAMA_BASE_URL=http://localhost:11434  # Optional, defaults to this URL

# Browser settings
CHROME_PATH=optional/path/to/chrome
PATIENT=false  # Set to true if API calls should wait for task completion
```

## LLM Provider Support

The server supports multiple LLM providers:

### OpenAI (Default)
- **Models**: gpt-4o (default), gpt-4, gpt-3.5-turbo, etc.
- **Setup**: Set `OPENAI_API_KEY` environment variable
- **Usage**: `--llm-provider openai --llm-model gpt-4o`

### Anthropic
- **Models**: claude-3-5-sonnet-20241022 (default), claude-3-opus-20240229, etc.
- **Setup**: Set `ANTHROPIC_API_KEY` environment variable
- **Usage**: `--llm-provider anthropic --llm-model claude-3-5-sonnet-20241022`
- **Requirements**: Install with `uv sync --extra anthropic` or `pip install langchain-anthropic`

### Ollama (Local)
- **Models**: llama3.1 (default), llama2, codellama, etc.
- **Setup**: Install and run [Ollama](https://ollama.ai/) locally
- **Usage**: `--llm-provider ollama --llm-model llama3.1`
- **Requirements**: Install with `uv sync --extra ollama` or `pip install langchain-ollama`

## Installation

```bash
# Install dependencies
uv sync
uv pip install playwright
uv run playwright install --with-deps --no-shell chromium
```

### Optional LLM Provider Dependencies

Choose one of the following installation methods based on your needs:

```bash
# Install with specific LLM providers
uv sync --extra anthropic          # For Anthropic models
uv sync --extra ollama             # For Ollama models
uv sync --extra all-llm            # For all LLM providers

# Or install manually
uv pip install langchain-anthropic  # For Anthropic models
uv pip install langchain-ollama     # For Ollama models

# For development with all dependencies
uv sync --extra all                # Includes test, dev, and all LLM providers
```

## Usage

### SSE Mode

```bash
# Run with default OpenAI provider
uv run server --port 8000

# Run with Anthropic provider
uv run server --port 8000 --llm-provider anthropic --llm-model claude-3-5-sonnet-20241022

# Run with Ollama provider (requires local Ollama server)
uv run server --port 8000 --llm-provider ollama --llm-model llama3.1
```

### stdio Mode

```bash
# 1. Build and install globally
uv build
uv tool uninstall browser-use-mcp-server 2>/dev/null || true
uv tool install dist/browser_use_mcp_server-*.whl

# 2. Run with stdio transport (OpenAI example)
browser-use-mcp-server run server --port 8000 --stdio --proxy-port 9000

# 3. Run with Anthropic provider
browser-use-mcp-server run server --port 8000 --stdio --proxy-port 9000 --llm-provider anthropic

# 4. Run with Ollama provider
browser-use-mcp-server run server --port 8000 --stdio --proxy-port 9000 --llm-provider ollama
```

### Development Mode (Absolute Path)

For development or when you want to run the server from any directory without installing:

```bash
# Run from any directory using absolute path
uv run --directory /path/to/browser-use-mcp-server server --port 8000

# Example with full path (replace with your actual path)
uv run --directory /Users/username/Projects/browser-use-mcp-server server --port 8000

# With LLM provider options
uv run --directory /path/to/browser-use-mcp-server server \
  --port 8000 \
  --llm-provider anthropic \
  --llm-model claude-3-5-sonnet-20241022

# For stdio mode with absolute path
uv run --directory /path/to/browser-use-mcp-server server \
  --port 8000 \
  --stdio \
  --proxy-port 9000 \
  --llm-provider ollama
```

**Benefits of absolute path usage:**
- No need to install the package globally
- Run from any working directory
- Useful for development and testing
- Easy integration with CI/CD pipelines
- Allows multiple versions/branches to coexist

## Client Configuration

### SSE Mode Client Configuration

```json
{
  "mcpServers": {
    "browser-use-mcp-server": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

### stdio Mode Client Configuration

#### OpenAI (Default)
```json
{
  "mcpServers": {
    "browser-server": {
      "command": "browser-use-mcp-server",
      "args": [
        "run",
        "server",
        "--port",
        "8000",
        "--stdio",
        "--proxy-port",
        "9000"
      ],
      "env": {
        "OPENAI_API_KEY": "your-openai-api-key"
      }
    }
  }
}
```

#### Anthropic
```json
{
  "mcpServers": {
    "browser-server": {
      "command": "browser-use-mcp-server",
      "args": [
        "run",
        "server",
        "--port",
        "8000",
        "--stdio",
        "--proxy-port",
        "9000",
        "--llm-provider",
        "anthropic",
        "--llm-model",
        "claude-3-5-sonnet-20241022"
      ],
      "env": {
        "ANTHROPIC_API_KEY": "your-anthropic-api-key"
      }
    }
  }
}
```

#### Ollama (Local)
```json
{
  "mcpServers": {
    "browser-server": {
      "command": "browser-use-mcp-server",
      "args": [
        "run",
        "server",
        "--port",
        "8000",
        "--stdio",
        "--proxy-port",
        "9000",
        "--llm-provider",
        "ollama",
        "--llm-model",
        "llama3.1"
      ]
    }
  }
}
```

### Development Mode Client Configuration (Absolute Path)

For development or when running from source without installing globally:

#### Using uv with absolute path
```json
{
  "mcpServers": {
    "browser-server": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/browser-use-mcp-server",
        "server",
        "--port",
        "8000",
        "--stdio",
        "--proxy-port",
        "9000"
      ],
      "env": {
        "OPENAI_API_KEY": "your-openai-api-key"
      }
    }
  }
}
```

#### With Anthropic provider (absolute path)
```json
{
  "mcpServers": {
    "browser-server": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/username/Projects/browser-use-mcp-server",
        "server",
        "--port",
        "8000",
        "--stdio",
        "--proxy-port",
        "9000",
        "--llm-provider",
        "anthropic",
        "--llm-model",
        "claude-3-5-sonnet-20241022"
      ],
      "env": {
        "ANTHROPIC_API_KEY": "your-anthropic-api-key"
      }
    }
  }
}
```

#### With Ollama provider (absolute path)
```json
{
  "mcpServers": {
    "browser-server": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/browser-use-mcp-server",
        "server",
        "--port",
        "8000",
        "--stdio",
        "--proxy-port",
        "9000",
        "--llm-provider",
        "ollama",
        "--llm-model",
        "llama3.1"
      ]
    }
  }
}
```

**Note**: Replace `/path/to/browser-use-mcp-server` with the actual absolute path to your cloned repository.

#### Getting the absolute path

To get the absolute path of your cloned repository for use in the configuration:

```bash
# Navigate to your cloned repository
cd /path/to/your/browser-use-mcp-server

# Get the absolute path
pwd
# Output: /Users/username/Projects/browser-use-mcp-server

# Or get it directly when cloning
git clone https://github.com/co-browser/browser-use-mcp-server.git
cd browser-use-mcp-server
pwd  # Use this path in your MCP client configuration
```

**Example workflow:**
1. Clone the repository: `git clone https://github.com/co-browser/browser-use-mcp-server.git`
2. Get the path: `cd browser-use-mcp-server && pwd`
3. Copy the output path (e.g., `/Users/username/Projects/browser-use-mcp-server`)
4. Use this path in your MCP client configuration as shown above

### Config Locations

| Client           | Configuration Path                                                |
| ---------------- | ----------------------------------------------------------------- |
| Cursor           | `./.cursor/mcp.json`                                              |
| Windsurf         | `~/.codeium/windsurf/mcp_config.json`                             |
| Claude (Mac)     | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Claude (Windows) | `%APPDATA%\Claude\claude_desktop_config.json`                     |

## Features

- [x] **Browser Automation**: Control browsers through AI agents
- [x] **Dual Transport**: Support for both SSE and stdio protocols
- [x] **VNC Streaming**: Watch browser automation in real-time
- [x] **Async Tasks**: Execute browser operations asynchronously

## Local Development

To develop and test the package locally:

### Option 1: Build and Install (Traditional)

1. Build a distributable wheel:

   ```bash
   # From the project root directory
   uv build
   ```

2. Install it as a global tool:

   ```bash
   uv tool uninstall browser-use-mcp-server 2>/dev/null || true
   uv tool install dist/browser_use_mcp_server-*.whl
   ```

3. Run from any directory:

   ```bash
   # Set your OpenAI API key for the current session
   export OPENAI_API_KEY=your-api-key-here

   # Or provide it inline for a one-time run
   OPENAI_API_KEY=your-api-key-here browser-use-mcp-server run server --port 8000 --stdio --proxy-port 9000
   ```

4. After making changes, rebuild and reinstall:
   ```bash
   uv build
   uv tool uninstall browser-use-mcp-server
   uv tool install dist/browser_use_mcp_server-*.whl
   ```

### Option 2: Direct Development (Recommended)

Use the absolute path method for faster development iteration:

```bash
# Run directly from source without installing
uv run --directory /path/to/browser-use-mcp-server server --port 8000

# With environment variables
OPENAI_API_KEY=your-key uv run --directory /path/to/browser-use-mcp-server server --port 8000

# Test different LLM providers
uv run --directory /path/to/browser-use-mcp-server server --port 8000 --llm-provider anthropic
```

**Benefits of Option 2:**
- No need to rebuild/reinstall after code changes
- Faster development cycle
- Easy to test multiple branches
- Works from any directory

## Docker

Using Docker provides a consistent and isolated environment for running the server.

```bash
# Build the Docker image
docker build -t browser-use-mcp-server .

# Run the container with the default VNC password ("browser-use")
# --rm ensures the container is automatically removed when it stops
# -p 8000:8000 maps the server port
# -p 5900:5900 maps the VNC port
docker run --rm -p8000:8000 -p5900:5900 browser-use-mcp-server

# Run with a custom VNC password read from a file
# Create a file (e.g., vnc_password.txt) containing only your desired password
echo "your-secure-password" > vnc_password.txt
# Mount the password file as a secret inside the container
docker run --rm -p8000:8000 -p5900:5900 \
  -v $(pwd)/vnc_password.txt:/run/secrets/vnc_password:ro \
  browser-use-mcp-server
```

*Note: The `:ro` flag in the volume mount (`-v`) makes the password file read-only inside the container for added security.*

### VNC Viewer

```bash
# Browser-based viewer
git clone https://github.com/novnc/noVNC
cd noVNC
./utils/novnc_proxy --vnc localhost:5900
```

Default password: `browser-use`

<div align="center">
  <img width="428" alt="VNC Screenshot" src="https://github.com/user-attachments/assets/45bc5bee-418d-4182-94f5-db84b4fc0b3a" />
  <br><br>
  <img width="428" alt="VNC Screenshot" src="https://github.com/user-attachments/assets/7db53f41-fc00-4e48-8892-f7108096f9c4" />
</div>

## Example

Try asking your AI:

```text
open https://news.ycombinator.com and return the top ranked article
```

## Support

For issues or inquiries: [cobrowser.xyz](https://cobrowser.xyz)

## Troubleshooting

### MCP stdio Mode Issues

If you're experiencing issues with MCP stdio mode in clients like Cursor:

#### "Unexpected token 'I', 'INFO ['" Error
This error occurs when logging output interferes with the MCP JSON protocol. The server now automatically handles this by redirecting all logging to stderr when `--stdio` mode is enabled.

**Solution**: Make sure you're using the latest version and include the `--stdio` flag:
```bash
uv run --directory /path/to/browser-use-mcp-server server --port 8000 --stdio --proxy-port 9000
```

#### "mcp-proxy not found" Error
This error occurs when the `mcp-proxy` tool is not installed or not in your PATH.

**Solution**: Install mcp-proxy:
```bash
uv tool install mcp-proxy
uv tool update-shell  # Restart your shell after this
```

#### Logging Configuration
- **SSE Mode**: Logs are formatted as JSON and sent to stderr
- **stdio Mode**: Logs are simplified and sent to stderr, stdout is reserved for MCP protocol
- **Log Levels**:
  - SSE mode: INFO level and above
  - stdio mode: ERROR level and above (to minimize noise)

### LLM Provider Issues

#### OpenAI API Key Not Found
```bash
export OPENAI_API_KEY=your-api-key-here
# Or pass it directly
uv run server --llm-api-key your-api-key-here
```

#### Anthropic API Key Not Found
```bash
export ANTHROPIC_API_KEY=your-api-key-here
# Or pass it directly
uv run server --llm-provider anthropic --llm-api-key your-api-key-here
```

#### Ollama Connection Issues
Make sure Ollama is running locally:
```bash
# Install Ollama from https://ollama.ai/
ollama serve  # Start the Ollama server
ollama pull llama3.1  # Pull the model you want to use
```

### Browser Issues

#### Chrome/Chromium Not Found
```bash
# Specify Chrome path explicitly
uv run server --chrome-path /path/to/chrome
```

#### Permission Denied Errors
Make sure the browser executable has proper permissions and the user can access it.

## Star History

<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=co-browser/browser-use-mcp-server&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=co-browser/browser-use-mcp-server&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=co-browser/browser-use-mcp-server&type=Date" />
  </picture>
</div>