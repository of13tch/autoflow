import os
from typing import Optional

import litellm
from litellm.exceptions import ContextWindowExceededError  # type: ignore
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
    MAX_DIFF_CHARS = 60_000
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


def generate_branch_name(diff_content: str) -> Optional[str]:
    """
    Generates a branch name suggestion based on the git diff content using litellm.
    """
    model = os.getenv("AUTOFLOW_LITELLM_MODEL", "gpt-3.5-turbo")
    verbose = os.getenv("AUTOFLOW_LITELLM_VERBOSE", "False").lower() == "true"

    if not diff_content.strip():
        console.print("[yellow]No diff content provided to generate branch name.[/yellow]")
        return None

    # Check for very large diffs (similar to commit message generation)
    # Max length can be adjusted, using a conservative value for now.
    MAX_DIFF_LENGTH_BRANCH = 60_000  # Slightly less than commit to be safe for prompts
    if len(diff_content) > MAX_DIFF_LENGTH_BRANCH:
        console.print(
            f"[yellow]Diff content is too large for branch name generation ({len(diff_content)} chars, max {MAX_DIFF_LENGTH_BRANCH}). "
            "Skipping automatic suggestion.[/yellow]"
        )
        return None

    system_prompt = """You are an expert at creating Git branch names. Based on the following git diff, suggest a concise, descriptive branch name.
The branch name should:
- Be in kebab-case (e.g., feature/user-authentication or fix/incorrect-calculation).
- Often start with a type like feat/, fix/, chore/, docs/, refactor/, test/, style/ if applicable.
- Be lowercase.
- Not contain spaces or special characters other than hyphens and slashes.
- Be relatively short but informative.
- Consist of a single line.
Output only the branch name itself, without any other text, explanation, or quotation marks."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Generate a branch name for the following diff:\n{diff_content}"},
    ]

    with console.status("[bold green]Generating branch name suggestion with LLM...", spinner="dots"):
        try:
            response = litellm.completion(
                model=model,
                messages=messages,
                temperature=0.5, # Slightly lower temp for more predictable branch names
                max_tokens=50,   # Branch names should be short
            )
            if verbose:
                console.print(f"LLM Raw Response for branch name: {response}")

            branch_name_suggestion = response.choices[0].message.content.strip()
            # Clean up potential markdown or quotes
            branch_name_suggestion = branch_name_suggestion.replace("`", "").replace("'", "").replace('"', "").strip()

            # Further ensure it's a single, valid-like segment
            if ' ' in branch_name_suggestion or '\\n' in branch_name_suggestion or not branch_name_suggestion:
                console.print(f"[yellow]LLM generated an invalid branch name format: '{branch_name_suggestion}'. Skipping.[/yellow]")
                return None


            return branch_name_suggestion if branch_name_suggestion else None

        except ContextWindowExceededError:
            console.print(
                "[bold red]Context window exceeded while generating branch name. "
                "The diff is too large for the selected model.[/bold red]"
            )
            return None
        except Exception as e:
            console.print(f"[bold red]Error generating branch name with litellm: {e}[/bold red]")
            if verbose:
                import traceback
                console.print(traceback.format_exc())
            return None
