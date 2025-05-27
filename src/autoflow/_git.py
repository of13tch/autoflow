import os
import re
import subprocess
from typing import Optional, Tuple

import click
from github import Github
from github.GithubException import GithubException
from rich.console import Console

from autoflow._exceptions import NoGithubRepoInfo, NoGithubTokenError, NoGitRepoDetected

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
    # Split message into subject and body for git commit -m
    lines = message.strip().split('\\n', 1)
    commit_args = ["git", "commit"]
    commit_args.extend(["-m", lines[0]])  # Subject
    if len(lines) > 1 and lines[1].strip():
        commit_args.extend(["-m", lines[1].strip()])  # Body

    result = run_git_command(commit_args, capture_output=True)  # Capture output to show to user
    if result and result.returncode == 0:
        if result.stdout:
            click.echo(result.stdout)
        return True
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


def get_remote_repo_info() -> Tuple[Optional[str], Optional[str]]:
    """
    Parse the GitHub remote URL to extract owner and repo name.
    Returns a tuple of (owner, repo_name) or (None, None) if not found.
    """
    # Get the GitHub remote URL
    result = run_git_command(["git", "remote", "get-url", "origin"])
    if not result or not result.stdout:
        console.print("[bold red]Failed to get remote URL.[/bold red]")
        return None, None

    remote_url = result.stdout.strip()

    # Parse the GitHub URL format: https://github.com/owner/repo.git or git@github.com:owner/repo.git
    https_pattern = r"https://github\.com/([^/]+)/([^/.]+)(?:\.git)?"
    ssh_pattern = r"git@github\.com:([^/]+)/([^/.]+)(?:\.git)?"

    https_match = re.match(https_pattern, remote_url)
    if https_match:
        return https_match.group(1), https_match.group(2)

    ssh_match = re.match(ssh_pattern, remote_url)
    if ssh_match:
        return ssh_match.group(1), ssh_match.group(2)

    console.print(f"[bold yellow]Could not parse GitHub repo info from {remote_url}[/bold yellow]")
    return None, None


def push_current_branch() -> bool:
    """
    Push the current branch to remote.
    Returns True if successful, False otherwise.
    """
    current_branch = get_current_branch()
    if not current_branch:
        console.print("[bold red]Could not determine current branch.[/bold red]")
        return False

    with console.status(f"[bold green]Pushing branch {current_branch} to remote...", spinner="dots"):
        result = run_git_command(["git", "push", "--set-upstream", "origin", current_branch])

        if result and result.returncode == 0:
            console.print(f"[bold green]Successfully pushed branch {current_branch} to remote.[/bold green]")
            return True

        console.print("[bold red]Failed to push branch to remote.[/bold red]")
        if result and result.stderr:
            console.print(f"[red]{result.stderr}[/red]")
        return False


def get_git_auth_token():
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        return github_token
    try:
        # Prepare the input for git credential fill
        input_data = "protocol=https\nhost=github.com\n\n"

        # Run the git credential fill command
        result = subprocess.run(["git", "credential", "fill"], input=input_data, capture_output=True, text=True)

        # Check if the command was successful
        if result.returncode == 0:
            output = result.stdout.strip()
            for line in output.splitlines():
                if line.startswith("password="):
                    return line.split("=", 1)[1]
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None


def create_pull_request(title: str, body: str, base_branch: str) -> Optional[str]:
    """
    Create a pull request on GitHub.

    Args:
        title: Title for the PR
        body: Description for the PR
        base_branch: Target branch for the PR (default: repository's default branch)

    Returns:
        URL of the created PR or None if failed
    """
    # Get GitHub token from environment
    github_token = get_git_auth_token()
    if not github_token:
        raise NoGithubTokenError

    # Get current branch
    head_branch = get_current_branch()
    if not head_branch:
        raise NoGitRepoDetected

    # Get repository info
    owner, repo_name = get_remote_repo_info()
    if not owner or not repo_name:
        raise NoGithubRepoInfo

    # Initialize GitHub client
    g = Github(github_token)

    repo = g.get_repo(f"{owner}/{repo_name}")
    pr = repo.create_pull(
        title=title,
        body=body,
        head=head_branch,
        base=base_branch
    )
    return pr.html_url
