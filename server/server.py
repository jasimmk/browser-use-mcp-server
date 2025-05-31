"""
Browser Use MCP Server

This module implements an MCP (Model-Control-Protocol) server for browser automation
using the browser_use library. It provides functionality to interact with a browser instance
via an async task queue, allowing for long-running browser tasks to be executed asynchronously
while providing status updates and results.

The server supports Server-Sent Events (SSE) for web-based interfaces.
"""

# Standard library imports
import asyncio
import json
import logging
import os
import sys

# Early stdio mode detection and configuration
# This must happen before any other imports that might log to stdout
if '--stdio' in sys.argv:
    # Immediately redirect stdout to prevent any logging interference
    class EarlyStdoutFilter:
        def __init__(self):
            self.stderr = sys.stderr
            self.original_stdout = sys.stdout

        def write(self, text):
            stripped = text.strip()
            if stripped:
                # If it looks like JSON (MCP protocol), let it through
                if stripped.startswith('{') and stripped.endswith('}'):
                    self.original_stdout.write(text)
                    self.original_stdout.flush()
                else:
                    # Redirect everything else to stderr
                    self.stderr.write(f"[EARLY-LOG] {text}")
                    self.stderr.flush()
            else:
                self.original_stdout.write(text)
                self.original_stdout.flush()

        def flush(self):
            self.original_stdout.flush()
            self.stderr.flush()

    # Replace stdout immediately
    sys.stdout = EarlyStdoutFilter()

    # Also configure basic logging to stderr immediately
    logging.basicConfig(
        level=logging.ERROR,
        format='%(levelname)s:%(name)s:%(message)s',
        stream=sys.stderr,
        force=True
    )

# Set up SSE transport
import threading
import time
import traceback
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, Union

# Third-party imports
import click
import mcp.types as types
import uvicorn

# Browser-use library imports
from browser_use import Agent
from browser_use.browser.browser import Browser, BrowserConfig
from browser_use.browser.context import BrowserContext, BrowserContextConfig
from dotenv import load_dotenv
from langchain_core.language_models import BaseLanguageModel

# LLM providers
from langchain_openai import ChatOpenAI

# MCP server components
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from pythonjsonlogger import jsonlogger
from starlette.applications import Starlette
from starlette.routing import Mount, Route

# Load environment variables
load_dotenv()


def configure_logging_for_stdio():
    """
    Configure logging specifically for MCP stdio mode.

    This ensures that ALL logging output goes to stderr and nothing
    interferes with the JSON protocol on stdout.
    """
    # Suppress all stdout output from third-party libraries
    import warnings
    warnings.filterwarnings("ignore")

    # Completely disable all existing loggers first
    logging.getLogger().handlers.clear()

    # Configure root logger to use stderr only with minimal output
    root_logger = logging.getLogger()
    root_logger.handlers = []

    # Create stderr handler with minimal formatting for stdio mode
    stderr_handler = logging.StreamHandler(sys.stderr)
    # Use simple formatter for stdio mode to reduce noise
    simple_formatter = logging.Formatter('%(levelname)s:%(name)s:%(message)s')
    stderr_handler.setFormatter(simple_formatter)
    root_logger.addHandler(stderr_handler)
    root_logger.setLevel(logging.ERROR)  # Only show errors in stdio mode

    # Aggressively configure all known problematic loggers
    loggers_to_silence = [
        "browser_use",
        "playwright",
        "mcp",
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
        "httpx",
        "httpcore",
        "asyncio",
        "langchain",
        "langchain_openai",
        "langchain_anthropic",
        "langchain_ollama",
        "openai",
        "anthropic",
        "ollama",
        "root",
        "",  # Root logger
    ]

    for logger_name in loggers_to_silence:
        logger = logging.getLogger(logger_name)
        logger.handlers = []
        logger.addHandler(stderr_handler)
        logger.setLevel(logging.ERROR)  # Only errors
        logger.propagate = False

    # Smart stdout redirection that preserves MCP protocol
    class MCPStdoutFilter:
        def __init__(self):
            self.stderr = sys.stderr
            self.original_stdout = sys.stdout

        def write(self, text):
            # Check if this looks like MCP protocol JSON
            stripped = text.strip()
            if stripped:
                # If it starts with { and ends with }, it might be MCP JSON
                if stripped.startswith('{') and stripped.endswith('}'):
                    # Let MCP protocol messages through to stdout
                    self.original_stdout.write(text)
                    self.original_stdout.flush()
                else:
                    # Redirect everything else to stderr with a prefix
                    self.stderr.write(f"[LOG] {text}")
                    self.stderr.flush()
            else:
                # Empty lines go to original stdout
                self.original_stdout.write(text)
                self.original_stdout.flush()

        def flush(self):
            self.original_stdout.flush()
            self.stderr.flush()

    # Replace stdout with our smart filter
    sys.stdout = MCPStdoutFilter()


# Check if we're in stdio mode and configure logging immediately
if '--stdio' in sys.argv:
    configure_logging_for_stdio()
else:
    # Configure logging normally for non-stdio mode
    logger = logging.getLogger()
    logger.handlers = []  # Remove any existing handlers
    handler = logging.StreamHandler(sys.stderr)
    formatter = jsonlogger.JsonFormatter(
        '{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","message":"%(message)s"}'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    # Ensure uvicorn also logs to stderr in JSON format
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.handlers = []
    uvicorn_logger.addHandler(handler)

    # Ensure all other loggers use the same format
    logging.getLogger("browser_use").addHandler(handler)
    logging.getLogger("playwright").addHandler(handler)
    logging.getLogger("mcp").addHandler(handler)

# Get logger instance for use throughout the module
logger = logging.getLogger(__name__)


def parse_bool_env(env_var: str, default: bool = False) -> bool:
    """
    Parse a boolean environment variable.

    Args:
        env_var: The environment variable name
        default: Default value if not set

    Returns:
        Boolean value of the environment variable
    """
    value = os.environ.get(env_var)
    if value is None:
        return default

    # Consider various representations of boolean values
    return value.lower() in ("true", "yes", "1", "y", "on")


def init_configuration() -> Dict[str, Any]:
    """
    Initialize configuration from environment variables with defaults.

    Returns:
        Dictionary containing all configuration parameters
    """
    config = {
        # Browser window settings
        "DEFAULT_WINDOW_WIDTH": int(os.environ.get("BROWSER_WINDOW_WIDTH", 1280)),
        "DEFAULT_WINDOW_HEIGHT": int(os.environ.get("BROWSER_WINDOW_HEIGHT", 1100)),
        # Browser config settings
        "DEFAULT_LOCALE": os.environ.get("BROWSER_LOCALE", "en-US"),
        "DEFAULT_USER_AGENT": os.environ.get(
            "BROWSER_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36",
        ),
        # Task settings
        "DEFAULT_TASK_EXPIRY_MINUTES": int(os.environ.get("TASK_EXPIRY_MINUTES", 60)),
        "DEFAULT_ESTIMATED_TASK_SECONDS": int(
            os.environ.get("ESTIMATED_TASK_SECONDS", 60)
        ),
        "CLEANUP_INTERVAL_SECONDS": int(
            os.environ.get("CLEANUP_INTERVAL_SECONDS", 3600)
        ),  # 1 hour
        "MAX_AGENT_STEPS": int(os.environ.get("MAX_AGENT_STEPS", 10)),
        # Browser arguments
        "BROWSER_ARGS": [
            "--no-sandbox",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-dev-shm-usage",
            "--remote-debugging-port=0",  # Use random port to avoid conflicts
        ],
        # Patient mode - if true, functions wait for task completion before returning
        "PATIENT_MODE": parse_bool_env("PATIENT", False),
    }

    return config


def create_llm(
    provider: str = "openai",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.0,
) -> BaseLanguageModel:
    """
    Create an LLM instance based on the specified provider.

    Args:
        provider: LLM provider ("openai", "anthropic", "ollama")
        model: Model name (provider-specific defaults if not specified)
        api_key: API key for the provider (uses environment variables if not specified)
        base_url: Base URL for the provider (for Ollama, defaults to http://localhost:11434)
        temperature: Temperature setting for the model

    Returns:
        Configured LLM instance

    Raises:
        ValueError: If provider is not supported or required dependencies are missing
        ImportError: If required packages are not installed
    """
    provider = provider.lower()

    if provider == "openai":
        # Use existing OpenAI implementation
        model = model or "gpt-4o"
        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable or pass api_key parameter.")

        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=api_key
        )

    elif provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            raise ImportError(
                "langchain-anthropic package is required for Anthropic models. "
                "Install it with: pip install langchain-anthropic"
            )

        model = model or "claude-3-5-sonnet-20241022"
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("Anthropic API key is required. Set ANTHROPIC_API_KEY environment variable or pass api_key parameter.")

        return ChatAnthropic(
            model=model,
            temperature=temperature,
            api_key=api_key
        )

    elif provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError:
            raise ImportError(
                "langchain-ollama package is required for Ollama models. "
                "Install it with: pip install langchain-ollama"
            )

        model = model or "llama3.1"
        base_url = base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

        return ChatOllama(
            model=model,
            temperature=temperature,
            base_url=base_url
        )

    else:
        raise ValueError(f"Unsupported LLM provider: {provider}. Supported providers: openai, anthropic, ollama")


# Initialize configuration
CONFIG = init_configuration()

# Task storage for async operations
task_store: Dict[str, Dict[str, Any]] = {}


async def create_browser_context_for_task(
    chrome_path: Optional[str] = None,
    window_width: int = CONFIG["DEFAULT_WINDOW_WIDTH"],
    window_height: int = CONFIG["DEFAULT_WINDOW_HEIGHT"],
    locale: str = CONFIG["DEFAULT_LOCALE"],
) -> Tuple[Browser, BrowserContext]:
    """
    Create a fresh browser and context for a task.

    This function creates an isolated browser instance and context
    with proper configuration for a single task.

    Args:
        chrome_path: Path to Chrome executable
        window_width: Browser window width
        window_height: Browser window height
        locale: Browser locale

    Returns:
        A tuple containing the browser instance and browser context

    Raises:
        Exception: If browser or context creation fails
    """
    try:
        # Create browser configuration
        browser_config = BrowserConfig(
            extra_chromium_args=CONFIG["BROWSER_ARGS"],
        )

        # Set chrome path if provided
        if chrome_path:
            browser_config.chrome_instance_path = chrome_path

        # Create browser instance
        browser = Browser(config=browser_config)

        # Create context configuration
        context_config = BrowserContextConfig(
            wait_for_network_idle_page_load_time=0.6,
            maximum_wait_page_load_time=1.2,
            minimum_wait_page_load_time=0.2,
            browser_window_size={"width": window_width, "height": window_height},
            locale=locale,
            user_agent=CONFIG["DEFAULT_USER_AGENT"],
            highlight_elements=True,
            viewport_expansion=0,
        )

        # Create context with the browser
        context = BrowserContext(browser=browser, config=context_config)

        return browser, context
    except Exception as e:
        logger.error(f"Error creating browser context: {str(e)}")
        raise


async def run_browser_task_async(
    task_id: str,
    url: str,
    action: str,
    llm: BaseLanguageModel,
    window_width: int = CONFIG["DEFAULT_WINDOW_WIDTH"],
    window_height: int = CONFIG["DEFAULT_WINDOW_HEIGHT"],
    locale: str = CONFIG["DEFAULT_LOCALE"],
) -> None:
    """
    Run a browser task asynchronously and store the result.

    This function executes a browser automation task with the given URL and action,
    and updates the task store with progress and results.

    When PATIENT_MODE is enabled, the calling function will wait for this function
    to complete before returning to the client.

    Args:
        task_id: Unique identifier for the task
        url: URL to navigate to
        action: Action to perform after navigation
        llm: Language model to use for browser agent
        window_width: Browser window width
        window_height: Browser window height
        locale: Browser locale
    """
    browser = None
    context = None

    try:
        # Update task status to running
        task_store[task_id]["status"] = "running"
        task_store[task_id]["start_time"] = datetime.now().isoformat()
        task_store[task_id]["progress"] = {
            "current_step": 0,
            "total_steps": 0,
            "steps": [],
        }

        # Define step callback function with the correct signature
        async def step_callback(
            browser_state: Any, agent_output: Any, step_number: int
        ) -> None:
            # Update progress in task store
            task_store[task_id]["progress"]["current_step"] = step_number
            task_store[task_id]["progress"]["total_steps"] = max(
                task_store[task_id]["progress"]["total_steps"], step_number
            )

            # Add step info with minimal details
            step_info = {"step": step_number, "time": datetime.now().isoformat()}

            # Add goal if available
            if agent_output and hasattr(agent_output, "current_state"):
                if hasattr(agent_output.current_state, "next_goal"):
                    step_info["goal"] = agent_output.current_state.next_goal

            # Add to progress steps
            task_store[task_id]["progress"]["steps"].append(step_info)

            # Log progress
            logger.info(f"Task {task_id}: Step {step_number} completed")

        # Define done callback function with the correct signature
        async def done_callback(history: Any) -> None:
            # Log completion
            logger.info(f"Task {task_id}: Completed with {len(history.history)} steps")

            # Add final step
            current_step = task_store[task_id]["progress"]["current_step"] + 1
            task_store[task_id]["progress"]["steps"].append(
                {
                    "step": current_step,
                    "time": datetime.now().isoformat(),
                    "status": "completed",
                }
            )

        # Get Chrome path from environment if available
        chrome_path = os.environ.get("CHROME_PATH")

        # Create a fresh browser and context for this task
        browser, context = await create_browser_context_for_task(
            chrome_path=chrome_path,
            window_width=window_width,
            window_height=window_height,
            locale=locale,
        )

        # Create agent with the fresh context
        agent = Agent(
            task=f"First, navigate to {url}. Then, {action}",
            llm=llm,
            browser_context=context,
            register_new_step_callback=step_callback,
            register_done_callback=done_callback,
        )

        # Run the agent with a reasonable step limit
        agent_result = await agent.run(max_steps=CONFIG["MAX_AGENT_STEPS"])

        # Get the final result
        final_result = agent_result.final_result()

        # Check if we have a valid result
        if final_result and hasattr(final_result, "raise_for_status"):
            final_result.raise_for_status()
            result_text = str(final_result.text)
        else:
            result_text = (
                str(final_result) if final_result else "No final result available"
            )

        # Gather essential information from the agent history
        is_successful = agent_result.is_successful()
        has_errors = agent_result.has_errors()
        errors = agent_result.errors()
        urls_visited = agent_result.urls()
        action_names = agent_result.action_names()
        extracted_content = agent_result.extracted_content()
        steps_taken = agent_result.number_of_steps()

        # Create a focused response with the most relevant information
        response_data = {
            "final_result": result_text,
            "success": is_successful,
            "has_errors": has_errors,
            "errors": [str(err) for err in errors if err],
            "urls_visited": [str(url) for url in urls_visited if url],
            "actions_performed": action_names,
            "extracted_content": extracted_content,
            "steps_taken": steps_taken,
        }

        # Store the result
        task_store[task_id]["status"] = "completed"
        task_store[task_id]["end_time"] = datetime.now().isoformat()
        task_store[task_id]["result"] = response_data

    except Exception as e:
        logger.error(f"Error in async browser task: {str(e)}")
        tb = traceback.format_exc()

        # Store the error
        task_store[task_id]["status"] = "failed"
        task_store[task_id]["end_time"] = datetime.now().isoformat()
        task_store[task_id]["error"] = str(e)
        task_store[task_id]["traceback"] = tb

    finally:
        # Clean up browser resources
        try:
            if context:
                await context.close()
            if browser:
                await browser.close()
            logger.info(f"Browser resources for task {task_id} cleaned up")
        except Exception as e:
            logger.error(
                f"Error cleaning up browser resources for task {task_id}: {str(e)}"
            )


async def cleanup_old_tasks() -> None:
    """
    Periodically clean up old completed tasks to prevent memory leaks.

    This function runs continuously in the background, removing tasks that have been
    completed or failed for more than 1 hour to conserve memory.
    """
    while True:
        try:
            # Sleep first to avoid cleaning up tasks too early
            await asyncio.sleep(CONFIG["CLEANUP_INTERVAL_SECONDS"])

            current_time = datetime.now()
            tasks_to_remove = []

            # Find completed tasks older than 1 hour
            for task_id, task_data in task_store.items():
                if (
                    task_data["status"] in ["completed", "failed"]
                    and "end_time" in task_data
                ):
                    end_time = datetime.fromisoformat(task_data["end_time"])
                    hours_elapsed = (current_time - end_time).total_seconds() / 3600

                    if hours_elapsed > 1:  # Remove tasks older than 1 hour
                        tasks_to_remove.append(task_id)

            # Remove old tasks
            for task_id in tasks_to_remove:
                del task_store[task_id]

            if tasks_to_remove:
                logger.info(f"Cleaned up {len(tasks_to_remove)} old tasks")

        except Exception as e:
            logger.error(f"Error in task cleanup: {str(e)}")


def create_mcp_server(
    llm: BaseLanguageModel,
    task_expiry_minutes: int = CONFIG["DEFAULT_TASK_EXPIRY_MINUTES"],
    window_width: int = CONFIG["DEFAULT_WINDOW_WIDTH"],
    window_height: int = CONFIG["DEFAULT_WINDOW_HEIGHT"],
    locale: str = CONFIG["DEFAULT_LOCALE"],
) -> Server:
    """
    Create and configure an MCP server for browser interaction.

    Args:
        llm: The language model to use for browser agent
        task_expiry_minutes: Minutes after which tasks are considered expired
        window_width: Browser window width
        window_height: Browser window height
        locale: Browser locale

    Returns:
        Configured MCP server instance
    """
    # Create MCP server instance
    app = Server("browser_use")

    @app.call_tool()
    async def call_tool(
        name: str, arguments: dict
    ) -> list[Union[types.TextContent, types.ImageContent, types.EmbeddedResource]]:
        """
        Handle tool calls from the MCP client.

        Args:
            name: The name of the tool to call
            arguments: The arguments to pass to the tool

        Returns:
            A list of content objects to return to the client.
            When PATIENT_MODE is enabled, the browser_use tool will wait for the task to complete
            and return the full result immediately instead of just the task ID.

        Raises:
            ValueError: If required arguments are missing
        """
        # Handle browser_use tool
        if name == "browser_use":
            # Check required arguments
            if "url" not in arguments:
                raise ValueError("Missing required argument 'url'")
            if "action" not in arguments:
                raise ValueError("Missing required argument 'action'")

            # Generate a task ID
            task_id = str(uuid.uuid4())

            # Initialize task in store
            task_store[task_id] = {
                "id": task_id,
                "status": "pending",
                "url": arguments["url"],
                "action": arguments["action"],
                "created_at": datetime.now().isoformat(),
            }

            # Start task in background
            _task = asyncio.create_task(
                run_browser_task_async(
                    task_id=task_id,
                    url=arguments["url"],
                    action=arguments["action"],
                    llm=llm,
                    window_width=window_width,
                    window_height=window_height,
                    locale=locale,
                )
            )

            # If PATIENT is set, wait for the task to complete
            if CONFIG["PATIENT_MODE"]:
                try:
                    await _task
                    # Return the completed task result instead of just the ID
                    task_data = task_store[task_id]
                    if task_data["status"] == "failed":
                        logger.error(
                            f"Task {task_id} failed: {task_data.get('error', 'Unknown error')}"
                        )
                    return [
                        types.TextContent(
                            type="text",
                            text=json.dumps(task_data, indent=2),
                        )
                    ]
                except Exception as e:
                    logger.error(f"Error in patient mode execution: {str(e)}")
                    traceback_str = traceback.format_exc()
                    # Update task store with error
                    task_store[task_id]["status"] = "failed"
                    task_store[task_id]["error"] = str(e)
                    task_store[task_id]["traceback"] = traceback_str
                    task_store[task_id]["end_time"] = datetime.now().isoformat()
                    # Return error information
                    return [
                        types.TextContent(
                            type="text",
                            text=json.dumps(task_store[task_id], indent=2),
                        )
                    ]

            # Return task ID immediately with explicit sleep instruction
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "task_id": task_id,
                            "status": "pending",
                            "message": f"Browser task started. Please wait for {CONFIG['DEFAULT_ESTIMATED_TASK_SECONDS']} seconds, then check the result using browser_get_result or the resource URI. Always wait exactly 5 seconds between status checks.",
                            "estimated_time": f"{CONFIG['DEFAULT_ESTIMATED_TASK_SECONDS']} seconds",
                            "resource_uri": f"resource://browser_task/{task_id}",
                            "sleep_command": "sleep 5",
                            "instruction": "Use the terminal command 'sleep 5' to wait 5 seconds between status checks. IMPORTANT: Always use exactly 5 seconds, no more and no less.",
                        },
                        indent=2,
                    ),
                )
            ]

        # Handle browser_get_result tool
        elif name == "browser_get_result":
            # Get result of async task
            if "task_id" not in arguments:
                raise ValueError("Missing required argument 'task_id'")

            task_id = arguments["task_id"]

            if task_id not in task_store:
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(
                            {"error": "Task not found", "task_id": task_id}, indent=2
                        ),
                    )
                ]

            # Get the current task data
            task_data = task_store[task_id].copy()

            # If task is still running, add simple guidance
            if task_data["status"] == "running":
                # Add a simple next check suggestion
                progress = task_data.get("progress", {})
                current_step = progress.get("current_step", 0)

                if current_step > 0:
                    # Simple message based on current step
                    task_data["message"] = (
                        f"Task is running (step {current_step}). Wait 5 seconds before checking again."
                    )
                    task_data["sleep_command"] = "sleep 5"
                    task_data["instruction"] = (
                        "Use the terminal command 'sleep 5' to wait 5 seconds before checking again. IMPORTANT: Always use exactly 5 seconds, no more and no less."
                    )
                else:
                    task_data["message"] = (
                        "Task is starting. Wait 5 seconds before checking again."
                    )
                    task_data["sleep_command"] = "sleep 5"
                    task_data["instruction"] = (
                        "Use the terminal command 'sleep 5' to wait 5 seconds before checking again. IMPORTANT: Always use exactly 5 seconds, no more and no less."
                    )

            # Return current task status and result if available
            return [
                types.TextContent(type="text", text=json.dumps(task_data, indent=2))
            ]

        else:
            raise ValueError(f"Unknown tool: {name}")

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        """
        List the available tools for the MCP client.

        Returns different tool descriptions based on the PATIENT_MODE configuration.
        When PATIENT_MODE is enabled, the browser_use tool description indicates it returns
        complete results directly. When disabled, it indicates async operation.

        Returns:
            A list of tool definitions appropriate for the current configuration
        """
        patient_mode = CONFIG["PATIENT_MODE"]

        if patient_mode:
            return [
                types.Tool(
                    name="browser_use",
                    description="Performs a browser action and returns the complete result directly (patient mode active)",
                    inputSchema={
                        "type": "object",
                        "required": ["url", "action"],
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL to navigate to",
                            },
                            "action": {
                                "type": "string",
                                "description": "Action to perform in the browser",
                            },
                        },
                    },
                ),
                types.Tool(
                    name="browser_get_result",
                    description="Gets the result of an asynchronous browser task (not needed in patient mode as browser_use returns complete results directly)",
                    inputSchema={
                        "type": "object",
                        "required": ["task_id"],
                        "properties": {
                            "task_id": {
                                "type": "string",
                                "description": "ID of the task to get results for",
                            }
                        },
                    },
                ),
            ]
        else:
            return [
                types.Tool(
                    name="browser_use",
                    description="Performs a browser action and returns a task ID for async execution",
                    inputSchema={
                        "type": "object",
                        "required": ["url", "action"],
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL to navigate to",
                            },
                            "action": {
                                "type": "string",
                                "description": "Action to perform in the browser",
                            },
                        },
                    },
                ),
                types.Tool(
                    name="browser_get_result",
                    description="Gets the result of an asynchronous browser task",
                    inputSchema={
                        "type": "object",
                        "required": ["task_id"],
                        "properties": {
                            "task_id": {
                                "type": "string",
                                "description": "ID of the task to get results for",
                            }
                        },
                    },
                ),
            ]

    @app.list_resources()
    async def list_resources() -> list[types.Resource]:
        """
        List the available resources for the MCP client.

        Returns:
            A list of resource definitions
        """
        # List all completed tasks as resources
        resources = []
        for task_id, task_data in task_store.items():
            if task_data["status"] in ["completed", "failed"]:
                resources.append(
                    types.Resource(
                        uri=f"resource://browser_task/{task_id}",
                        title=f"Browser Task Result: {task_id[:8]}",
                        description=f"Result of browser task for URL: {task_data.get('url', 'unknown')}",
                    )
                )
        return resources

    @app.read_resource()
    async def read_resource(uri: str) -> list[types.ResourceContents]:
        """
        Read a resource for the MCP client.

        Args:
            uri: The URI of the resource to read

        Returns:
            The contents of the resource
        """
        # Extract task ID from URI
        if not uri.startswith("resource://browser_task/"):
            return [
                types.ResourceContents(
                    type="text",
                    text=json.dumps(
                        {"error": f"Invalid resource URI: {uri}"}, indent=2
                    ),
                )
            ]

        task_id = uri.replace("resource://browser_task/", "")
        if task_id not in task_store:
            return [
                types.ResourceContents(
                    type="text",
                    text=json.dumps({"error": f"Task not found: {task_id}"}, indent=2),
                )
            ]

        # Return task data
        return [
            types.ResourceContents(
                type="text", text=json.dumps(task_store[task_id], indent=2)
            )
        ]

    # Add cleanup_old_tasks function to app for later scheduling
    app.cleanup_old_tasks = cleanup_old_tasks

    return app


@click.command()
@click.option("--port", default=8000, help="Port to listen on for SSE")
@click.option(
    "--proxy-port",
    default=None,
    type=int,
    help="Port for the proxy to listen on. If specified, enables proxy mode.",
)
@click.option("--chrome-path", default=None, help="Path to Chrome executable")
@click.option(
    "--window-width",
    default=CONFIG["DEFAULT_WINDOW_WIDTH"],
    help="Browser window width",
)
@click.option(
    "--window-height",
    default=CONFIG["DEFAULT_WINDOW_HEIGHT"],
    help="Browser window height",
)
@click.option("--locale", default=CONFIG["DEFAULT_LOCALE"], help="Browser locale")
@click.option(
    "--task-expiry-minutes",
    default=CONFIG["DEFAULT_TASK_EXPIRY_MINUTES"],
    help="Minutes after which tasks are considered expired",
)
@click.option(
    "--stdio",
    is_flag=True,
    default=False,
    help="Enable stdio mode. If specified, enables proxy mode.",
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
def main(
    port: int,
    proxy_port: Optional[int],
    chrome_path: str,
    window_width: int,
    window_height: int,
    locale: str,
    task_expiry_minutes: int,
    stdio: bool,
    llm_provider: str,
    llm_model: Optional[str],
    llm_api_key: Optional[str],
    llm_base_url: Optional[str],
    llm_temperature: float,
) -> int:
    """
    Run the browser-use MCP server.

    This function initializes the MCP server and runs it with the SSE transport.
    Each browser task will create its own isolated browser context.

    The server can run in two modes:
    1. Direct SSE mode (default): Just runs the SSE server
    2. Proxy mode (enabled by --stdio or --proxy-port): Runs both SSE server and mcp-proxy

    LLM Provider Support:
    - OpenAI: Requires OPENAI_API_KEY environment variable or --llm-api-key
    - Anthropic: Requires ANTHROPIC_API_KEY environment variable or --llm-api-key
    - Ollama: Requires local Ollama server running (default: http://localhost:11434)

    Args:
        port: Port to listen on for SSE
        proxy_port: Port for the proxy to listen on. If specified, enables proxy mode.
        chrome_path: Path to Chrome executable
        window_width: Browser window width
        window_height: Browser window height
        locale: Browser locale
        task_expiry_minutes: Minutes after which tasks are considered expired
        stdio: Enable stdio mode. If specified, enables proxy mode.
        llm_provider: LLM provider to use
        llm_model: LLM model name
        llm_api_key: API key for the LLM provider
        llm_base_url: Base URL for the LLM provider
        llm_temperature: Temperature setting for the LLM model

    Returns:
        Exit code (0 for success)
    """
    # Store Chrome path in environment variable if provided
    if chrome_path:
        os.environ["CHROME_PATH"] = chrome_path
        logger.info(f"Using Chrome path: {chrome_path}")
    else:
        logger.info(
            "No Chrome path specified, letting Playwright use its default browser"
        )

    # Initialize LLM with user-specified provider and options
    try:
        llm = create_llm(
            provider=llm_provider,
            model=llm_model,
            api_key=llm_api_key,
            base_url=llm_base_url,
            temperature=llm_temperature,
        )
        logger.info(f"Initialized LLM provider: {llm_provider}")
        if llm_model:
            logger.info(f"Using model: {llm_model}")
    except (ValueError, ImportError) as e:
        logger.error(f"Failed to initialize LLM: {str(e)}")
        return 1

    # Create MCP server
    app = create_mcp_server(
        llm=llm,
        task_expiry_minutes=task_expiry_minutes,
        window_width=window_width,
        window_height=window_height,
        locale=locale,
    )

    sse = SseServerTransport("/messages/")

    # Create the Starlette app for SSE
    async def handle_sse(request):
        """Handle SSE connections from clients."""
        try:
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await app.run(
                    streams[0], streams[1], app.create_initialization_options()
                )
        except Exception as e:
            logger.error(f"Error in handle_sse: {str(e)}")
            raise

    starlette_app = Starlette(
        debug=True,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )

    # Add startup event
    @starlette_app.on_event("startup")
    async def startup_event():
        """Initialize the server on startup."""
        logger.info("Starting MCP server...")

        # Sanity checks for critical configuration
        if port <= 0 or port > 65535:
            logger.error(f"Invalid port number: {port}")
            raise ValueError(f"Invalid port number: {port}")

        if window_width <= 0 or window_height <= 0:
            logger.error(f"Invalid window dimensions: {window_width}x{window_height}")
            raise ValueError(
                f"Invalid window dimensions: {window_width}x{window_height}"
            )

        if task_expiry_minutes <= 0:
            logger.error(f"Invalid task expiry minutes: {task_expiry_minutes}")
            raise ValueError(f"Invalid task expiry minutes: {task_expiry_minutes}")

        # Start background task cleanup
        asyncio.create_task(app.cleanup_old_tasks())
        logger.info("Task cleanup process scheduled")

    # Function to run uvicorn in a separate thread
    def run_uvicorn():
        # Configure uvicorn to use JSON logging
        log_config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                    "fmt": '{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","message":"%(message)s"}',
                }
            },
            "handlers": {
                "default": {
                    "formatter": "json",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stderr",
                }
            },
            "loggers": {
                "": {"handlers": ["default"], "level": "INFO"},
                "uvicorn": {"handlers": ["default"], "level": "INFO"},
                "uvicorn.error": {"handlers": ["default"], "level": "INFO"},
                "uvicorn.access": {"handlers": ["default"], "level": "INFO"},
            },
        }

        uvicorn.run(
            starlette_app,
            host="0.0.0.0",  # nosec
            port=port,
            log_config=log_config,
            log_level="info",
        )

    # If proxy mode is enabled, run both the SSE server and mcp-proxy
    if stdio:
        import subprocess  # nosec

        # Start the SSE server in a separate thread
        sse_thread = threading.Thread(target=run_uvicorn)
        sse_thread.daemon = True
        sse_thread.start()

        # Give the SSE server a moment to start
        time.sleep(1)

        proxy_cmd = [
            "mcp-proxy",
            f"http://localhost:{port}/sse",
            "--sse-port",
            str(proxy_port),
            "--allow-origin",
            "*",
        ]

        logger.info(f"Running proxy command: {' '.join(proxy_cmd)}")
        logger.info(
            f"SSE server running on port {port}, proxy running on port {proxy_port}"
        )

        try:
            # Using trusted command arguments from CLI parameters
            with subprocess.Popen(proxy_cmd) as proxy_process:  # nosec
                proxy_process.wait()
        except FileNotFoundError:
            logger.error("mcp-proxy not found. Please install it with: uv tool install mcp-proxy")
            logger.error("Or ensure it's in your PATH if installed differently.")
            logger.error("For more information, see: https://github.com/sparfenyuk/mcp-proxy")
            return 1
        except Exception as e:
            logger.error(f"Error starting mcp-proxy: {str(e)}")
            logger.error(f"Command was: {' '.join(proxy_cmd)}")
            logger.error("Make sure mcp-proxy is installed and accessible in your PATH.")
            return 1
    else:
        logger.info(f"Running in direct SSE mode on port {port}")
        run_uvicorn()

    return 0


if __name__ == "__main__":
    main()
