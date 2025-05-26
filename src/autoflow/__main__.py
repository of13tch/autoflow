import os
import subprocess

import click
import litellm


def run_git_command(command, check=True, capture_output=True, text=True):
    """Helper to run git commands."""
    try:
        return subprocess.run(command, check=check, capture_output=capture_output, text=text)
    except subprocess.CalledProcessError as e:
        click.echo(click.style(f"Git command failed: {' '.join(command)}", fg="red"))
        click.echo(click.style(f"Error: {e}", fg="red"))
        if e.stdout:
            click.echo(click.style(f"Stdout: {e.stdout}", fg="yellow"))
        if e.stderr:
            click.echo(click.style(f"Stderr: {e.stderr}", fg="yellow"))
        return None
    except FileNotFoundError:
        click.echo(click.style("Error: Git command not found. Is Git installed and in your PATH?", fg="red"))
        return None


def get_current_branch():
    """Gets the current Git branch."""
    result = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    return result.stdout.strip() if result and result.stdout else None


def get_default_branch():
    """Gets the default branch name (e.g., main, master) by inspecting origin/HEAD."""
    result = run_git_command(["git", "rev-parse", "--abbrev-ref", "origin/HEAD"])
    if result and result.stdout:
        return result.stdout.strip().replace("origin/", "")
    # Fallback if origin/HEAD is not set or no remote named origin
    common_defaults = ["main", "master"]
    for branch in common_defaults:
        check_local = run_git_command(["git", "show-ref", "--verify", f"refs/heads/{branch}"], capture_output=False)
        if check_local and check_local.returncode == 0:
            return branch
        check_remote = run_git_command(["git", "show-ref", "--verify", f"refs/remotes/origin/{branch}"], capture_output=False)
        if check_remote and check_remote.returncode == 0:
            return branch
    return None


def check_for_unstaged_changes():
    """Checks if there are any unstaged changes."""
    result = run_git_command(["git", "status", "--porcelain"])
    return bool(result and result.stdout.strip())


def stage_all_changes():
    """Stages all changes (git add .)."""
    click.echo("Staging all changes...")
    result = run_git_command(["git", "add", "."])
    if result and result.returncode == 0:
        click.echo(click.style("Successfully staged changes.", fg="green"))
        return True
    click.echo(click.style("Failed to stage changes.", fg="red"))
    return False


def create_and_checkout_branch(branch_name):
    """Creates and checks out a new branch."""
    click.echo(f"Creating and checking out new branch: {branch_name}...")
    result = run_git_command(["git", "checkout", "-b", branch_name])
    if result and result.returncode == 0:
        click.echo(click.style(f"Successfully created and checked out branch '{branch_name}'.", fg="green"))
        return True
    click.echo(click.style(f"Failed to create or checkout branch '{branch_name}'.", fg="red"))
    return False


def git_commit_with_message(message):
    """Commits staged changes with the given message."""
    click.echo("Committing with message...")
    # Split message into subject and body for git commit -m
    lines = message.strip().split('\\n', 1)
    commit_args = ["git", "commit"]
    commit_args.extend(["-m", lines[0]]) # Subject
    if len(lines) > 1 and lines[1].strip():
        commit_args.extend(["-m", lines[1].strip()]) # Body

    result = run_git_command(commit_args, capture_output=True) # Capture output to show to user
    if result and result.returncode == 0:
        click.echo(click.style("Successfully committed.", fg="green"))
        if result.stdout:
            click.echo(result.stdout)
        return True
    click.echo(click.style("Failed to commit.", fg="red"))
    if result and result.stderr:
        click.echo(result.stderr)
    elif result and result.stdout: # Sometimes commit errors go to stdout
        click.echo(result.stdout)
    return False


def get_git_diff():
    """Returns the output of git diff --staged, excluding common lock files."""
    # Common lock file patterns to exclude.
    # Using pathspecs for exclusion: :(exclude)pattern
    excluded_patterns = [
        ":(exclude)uv.lock",
        ":(exclude)poetry.lock",
        ":(exclude)Pipfile.lock",
        ":(exclude)package-lock.json",
        ":(exclude)yarn.lock",
        ":(exclude)pnpm-lock.yaml",
        ":(exclude)composer.lock", # PHP
        ":(exclude)Gemfile.lock"  # Ruby
    ]

    command = ["git", "diff", "--staged", "--"] + excluded_patterns

    # If no specific files/patterns are given to diff after '--', 
    # it implies diffing everything not explicitly excluded in the current directory.
    # To ensure it diffs all staged files respecting exclusions, we can add '.'
    # However, git diff --staged with pathspecs should work correctly.
    # Let's ensure it targets the whole repo context for staged files.
    # The command should be `git diff --staged -- . pathspec1 pathspec2`
    # Actually, `git diff --staged -- pathspec1 pathspec2` is fine.
    # The '--' separates options from pathspecs.

    diff_process = run_git_command(command) # Use the existing helper

    if diff_process and diff_process.stdout:
        return diff_process.stdout
    elif diff_process and not diff_process.stdout:
        # No diff, or only excluded files were staged
        return "" 
    # Error handling is done in run_git_command, which would return None
    return None


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
        click.echo(click.style(
            f"Warning: Diff content is very large ({len(diff_content)} chars, limit is {MAX_DIFF_CHARS} chars). "
            "Using a generic commit message to avoid exceeding LLM context window.", 
            fg="yellow"
        ))
        return "refactor: Apply extensive changes (diff too large for detailed AI summary)"

    try:
        response = litellm.completion(
            model=model, # Use the configured model
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert assistant that generates concise, short, and informative commit messages based on git diffs. Follow standard commit message conventions: use the imperative mood, limit the subject line (if possible, imagine a 50-character limit), and focus on what changed and why, not just how. Avoid overly long descriptions."
                },
                {
                    "role": "user",
                    "content": f"Please generate a commit message for the following changes:\n\n{diff_content}",
                },
            ],
        )
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            return response.choices[0].message.content.strip()
        else:
            return "Could not generate commit message."
    except Exception as e:
        click.echo(f"Error generating commit message with litellm: {e}")
        return "Error generating commit message."


@click.group(invoke_without_command=True) # Modified
@click.pass_context # Added
def main(ctx): # Modified
    """A CLI to help write good commit messages whilst preserving the flow."""
    if ctx.invoked_subcommand is None: # Added
        ctx.invoke(commit) # Added


@main.command()
@click.pass_context
def commit(ctx):
    """Manages branching, staging, and committing changes with an AI-generated message."""
    current_branch = get_current_branch()
    if not current_branch:
        click.echo(click.style("Could not determine current branch. Exiting.", fg="red"))
        return

    default_branch = get_default_branch()
    # click.echo(f"Current branch: {current_branch}, Default branch: {default_branch}") # For debugging

    if default_branch and current_branch == default_branch:
        if click.confirm(click.style(f"You are on the default branch ('{current_branch}'). Do you want to create a new branch?", fg="yellow"), default=True):
            new_branch_name = click.prompt(click.style("Enter the name for the new branch", fg="cyan"))
            if not new_branch_name.strip():
                click.echo(click.style("Branch name cannot be empty. Aborting commit.", fg="red"))
                return
            if not create_and_checkout_branch(new_branch_name):
                click.echo(click.style("Failed to create new branch. Aborting commit.", fg="red"))
                return
            current_branch = new_branch_name # Update current branch for subsequent operations
        else:
            click.echo(click.style("Proceeding with commit on the default branch.", fg="yellow"))

    if check_for_unstaged_changes():
        if click.confirm(click.style("You have unstaged changes. Do you want to stage them all?", fg="yellow"), default=True):
            if not stage_all_changes():
                click.echo(click.style("Failed to stage changes. Please stage them manually or resolve issues.", fg="red"))
                # Optionally, allow proceeding without staging or exit
                if not click.confirm("Proceed without staging all changes?", default=False):
                    return
        else:
            click.echo(click.style("Proceeding without staging new changes. Only previously staged changes will be committed.", fg="yellow"))


    diff_content = get_git_diff() # Get diff of (now potentially all) staged changes
    if not diff_content: # Check if there's anything staged to commit
        click.echo("No staged changes found to commit.")
        # Check if there are unstaged changes they might have forgotten
        if check_for_unstaged_changes():
            click.echo(click.style("However, there are unstaged changes. Did you mean to stage them?", fg="yellow"))
        return

    click.echo("Generating commit message...")
    commit_message = generate_commit_message(diff_content)

    click.echo("\\nSuggested commit message:")
    click.echo(click.style("-------------------------", fg="blue"))
    click.echo(click.style(commit_message, fg="green"))
    click.echo(click.style("-------------------------", fg="blue"))

    if click.confirm(click.style("Do you want to commit with this message?", fg="yellow"), default=True):
        if git_commit_with_message(commit_message):
            click.echo(click.style("Commit successful!", fg="green"))
        else:
            click.echo(click.style("Commit failed or was aborted.", fg="red"))
    else:
        click.echo("Commit aborted by user.")


if __name__ == "__main__":
    main()
