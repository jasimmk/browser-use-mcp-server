"""
Command line interface for browser-use-mcp-server.

This module provides a command-line interface for starting the browser-use MCP server.
It wraps the existing server functionality with a CLI.
"""

import json
import logging
import sys
from typing import Optional

import click
from pythonjsonlogger import jsonlogger

# Import directly from our package
from browser_use_mcp_server.server import main as server_main

# Configure logging for CLI
logger = logging.getLogger()
logger.handlers = []  # Remove any existing handlers
handler = logging.StreamHandler(sys.stderr)
formatter = jsonlogger.JsonFormatter(
    '{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","message":"%(message)s"}'
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)


def log_error(message: str, error: Optional[Exception] = None):
    """Log error in JSON format to stderr"""
    error_data = {"error": message, "traceback": str(error) if error else None}
    print(json.dumps(error_data), file=sys.stderr)


@click.group()
def cli():
    """Browser-use MCP server command line interface."""


@cli.command()
@click.argument("subcommand")
@click.option("--port", default=8000, help="Port to listen on for SSE")
@click.option(
    "--proxy-port",
    default=None,
    type=int,
    help="Port for the proxy to listen on (when using stdio mode)",
)
@click.option("--chrome-path", default=None, help="Path to Chrome executable")
@click.option("--window-width", default=1280, help="Browser window width")
@click.option("--window-height", default=1100, help="Browser window height")
@click.option("--locale", default="en-US", help="Browser locale")
@click.option(
    "--task-expiry-minutes",
    default=60,
    help="Minutes after which tasks are considered expired",
)
@click.option(
    "--stdio", is_flag=True, default=False, help="Enable stdio mode with mcp-proxy"
)
@click.option(
    "--llm-provider",
    default="openai",
    type=click.Choice(["openai", "anthropic", "ollama"], case_sensitive=False),
    help="LLM provider to use (openai, anthropic, ollama)",
)
@click.option(
    "--llm-model",
    default=None,
    help="LLM model name (uses provider defaults if not specified)",
)
@click.option(
    "--llm-api-key",
    default=None,
    help="API key for the LLM provider (uses environment variables if not specified)",
)
@click.option(
    "--llm-base-url",
    default=None,
    help="Base URL for the LLM provider (for Ollama, defaults to http://localhost:11434)",
)
@click.option(
    "--llm-temperature",
    default=0.0,
    type=float,
    help="Temperature setting for the LLM model",
)
def run(
    subcommand,
    port,
    proxy_port,
    chrome_path,
    window_width,
    window_height,
    locale,
    task_expiry_minutes,
    stdio,
    llm_provider,
    llm_model,
    llm_api_key,
    llm_base_url,
    llm_temperature,
):
    """Run the browser-use MCP server.

    SUBCOMMAND: should be 'server'

    LLM Provider Support:
    - OpenAI: Requires OPENAI_API_KEY environment variable or --llm-api-key
    - Anthropic: Requires ANTHROPIC_API_KEY environment variable or --llm-api-key
    - Ollama: Requires local Ollama server running (default: http://localhost:11434)
    """
    if subcommand != "server":
        log_error(f"Unknown subcommand: {subcommand}. Only 'server' is supported.")
        sys.exit(1)

    try:
        # We need to construct the command line arguments to pass to the server's Click command
        old_argv = sys.argv.copy()

        # Build a new argument list for the server command
        new_argv = [
            "server",  # Program name
            "--port",
            str(port),
        ]

        if chrome_path:
            new_argv.extend(["--chrome-path", chrome_path])

        if proxy_port is not None:
            new_argv.extend(["--proxy-port", str(proxy_port)])

        new_argv.extend(["--window-width", str(window_width)])
        new_argv.extend(["--window-height", str(window_height)])
        new_argv.extend(["--locale", locale])
        new_argv.extend(["--task-expiry-minutes", str(task_expiry_minutes)])

        if stdio:
            new_argv.append("--stdio")

        # Add LLM provider options
        new_argv.extend(["--llm-provider", llm_provider])

        if llm_model:
            new_argv.extend(["--llm-model", llm_model])

        if llm_api_key:
            new_argv.extend(["--llm-api-key", llm_api_key])

        if llm_base_url:
            new_argv.extend(["--llm-base-url", llm_base_url])

        new_argv.extend(["--llm-temperature", str(llm_temperature)])

        # Replace sys.argv temporarily
        sys.argv = new_argv

        # Run the server's command directly
        try:
            return server_main()
        finally:
            # Restore original sys.argv
            sys.argv = old_argv

    except Exception as e:
        log_error("Error starting server", e)
        sys.exit(1)


if __name__ == "__main__":
    cli()
