import os

import litellm
from rich.console import Console

console = Console()


def generate_commit_message(diff_content):
    """Generates a commit message using litellm based on the diff content."""
    if diff_content is None: # Error occurred in get_git_diff
        return "Error retrieving git diff."
    if not diff_content.strip():
        return "No applicable changes to commit (lock files might have been excluded)."

    # Configure litellm from environment variables
    model = os.getenv("AUTOFLOW_LITELLM_MODEL", "gpt-3.5-turbo")
    verbose_str = os.getenv("AUTOFLOW_LITELLM_VERBOSE", "False").lower()
    litellm.set_verbose = verbose_str in ("true", "1", "t", "yes")

    # Check for excessively large diff content to prevent ContextWindowExceededError
    # OpenAI's gpt-3.5-turbo has a context window of ~16k tokens.
    # 1 token ~ 4 chars. Let's set a conservative char limit, e.g., 60,000.
    # The prompt itself also consumes tokens.
    MAX_DIFF_CHARS = 60000
    if len(diff_content) > MAX_DIFF_CHARS:
        console.print(
            f"[yellow]Warning: Diff content is very large ({len(diff_content)} chars, limit is {MAX_DIFF_CHARS} chars). "
            "Using a generic commit message to avoid exceeding LLM context window.[/yellow]"
        )
        return "refactor: Apply extensive changes (diff too large for detailed AI summary)"

    try:
        with console.status("[bold green]Querying LLM for commit message...", spinner="dots"):
            response = litellm.completion(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert assistant that generates concise, short, and informative commit messages based on git diffs. Follow standard commit message conventions: use the imperative mood, limit the subject line (if possible, imagine a 50-character limit), and focus on what changed and why, not just how. Avoid overly long descriptions."
                    },
                    {
                        "role": "user",
                        "content": f"Please generate a commit message for the following changes:\\n\\n{diff_content}",
                    },
                ],
            )
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            return response.choices[0].message.content.strip()
        else:
            console.print("[bold red]Could not generate commit message from LLM.[/bold red]")
            return "Could not generate commit message."
    except Exception as e:
        console.print(f"[bold red]Error generating commit message with litellm: {e}[/bold red]")
        return "Error generating commit message."
