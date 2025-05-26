import subprocess

import click
from rich.console import Console

console = Console()


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
    with console.status("[bold green]Staging all changes...", spinner="dots") as status:  # Modified
        result = run_git_command(["git", "add", "."])
        if result and result.returncode == 0:
            status.update("[bold green]Successfully staged changes.[/bold green]")  # Modified
            return True
        console.print("[bold red]Failed to stage changes.[/bold red]")  # Modified
        return False


def create_and_checkout_branch(branch_name):
    """Creates and checks out a new branch."""
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
    commit_args.extend(["-m", lines[0]])  # Subject
    if len(lines) > 1 and lines[1].strip():
        commit_args.extend(["-m", lines[1].strip()])  # Body

    result = run_git_command(commit_args, capture_output=True)  # Capture output to show to user
    if result and result.returncode == 0:
        click.echo(click.style("Successfully committed.", fg="green"))
        if result.stdout:
            click.echo(result.stdout)
        return True
    click.echo(click.style("Failed to commit.", fg="red"))
    if result and result.stderr:
        click.echo(result.stderr)
    elif result and result.stdout:  # Sometimes commit errors go to stdout
        click.echo(result.stdout)
    return False


def get_git_diff(staged=True):
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
        ":(exclude)composer.lock",  # PHP
        ":(exclude)Gemfile.lock"  # Ruby
    ]

    # If staged is True, we use `git diff --staged`
    if staged:
        command = ["git", "diff", "--staged", "--"] + excluded_patterns
    else:
        command = ["git", "diff", "--"] + excluded_patterns

    # If no specific files/patterns are given to diff after '--',
    # it implies diffing everything not explicitly excluded in the current directory.
    # To ensure it diffs all staged files respecting exclusions, we can add '.'
    # However, git diff --staged with pathspecs should work correctly.
    # Let's ensure it targets the whole repo context for staged files.
    # The command should be `git diff --staged -- . pathspec1 pathspec2`
    # Actually, `git diff --staged -- pathspec1 pathspec2` is fine.
    # The '--' separates options from pathspecs.

    diff_process = run_git_command(command)  # Use the existing helper

    if diff_process and diff_process.stdout:
        return diff_process.stdout
    elif diff_process and not diff_process.stdout:
        # No diff, or only excluded files were staged
        return ""
    # Error handling is done in run_git_command, which would return None
    return None
