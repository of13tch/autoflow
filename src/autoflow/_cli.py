import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from autoflow._git import (
    create_and_checkout_branch,
    create_pull_request,
    get_current_branch,
    get_default_branch,
    get_git_diff,
    git_commit_with_message,
    push_current_branch,
    stage_all_changes,
)
from autoflow._litellm import generate_branch_name, generate_commit_message, generate_pr_description

console = Console()


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """A CLI to help write good commit messages whilst preserving the flow."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(commit)


@main.command()
def commit():
    """Manages branching, staging, and committing changes with an AI-generated message."""
    current_branch_name = get_current_branch()
    if not current_branch_name:
        console.print("[bold red]Could not determine current branch. Exiting.[/bold red]")
        return

    default_branch_name = get_default_branch()
    diff = get_git_diff(staged=False)
    if diff is None:
        console.print("[bold red]Could not get git diff. Exiting.[/bold red]")
        return

    if default_branch_name and current_branch_name == default_branch_name:
        with console.status("Generating branch name from unstaged changes...", spinner="dots"):
            console.print(f"You are on the default branch: {default_branch_name}")
            branch_name = generate_branch_name(diff)
            if branch_name is None:
                console.print("[bold red]Failed to generate branch name. Aborting commit.[/bold red]")
                return

        if console.input(f"Use generated branch name {branch_name}? (y/N): ").strip().lower() == 'y':
            create_and_checkout_branch(branch_name)
        else:
            console.print("Proceeding with commit on the default branch.")

    if not stage_all_changes():
        console.print("[bold red]Aborting commit due to staging issues.[/bold red]")
        return

    diff_content = get_git_diff()

    if diff_content is None:
        console.print("[bold red]Could not get git diff. Exiting.[/bold red]")
        return

    with console.status("Generating commit message..."):
        try:
            commit_message = generate_commit_message(diff_content)
        except Exception as e:
            console.print(f"[bold red]Error generating commit message: {e}[/bold red]")
            return

    console.print(Panel(Text(commit_message, style="green"), title="[bold blue]Suggested Commit Message[/bold blue]", expand=False))

    # Final confirmation
    if console.input("Commit & Push with this message? (Y/n): ").strip().lower() != 'n':
        git_commit_with_message(commit_message)
    else:
        console.print("[red]Commit aborted by user.[/red]")

    if not push_current_branch():
        console.print("[bold red]Failed to push branch to remote. Aborting PR creation.[/bold red]")
        return

    return default_branch_name, current_branch_name, commit_message, diff_content


@main.command()
@click.pass_context
def pr(ctx):
    """Creates a pull request with an AI-generated description based on the latest commit."""
    default_branch_name, current_branch_name, commit_message, diff_content = ctx.invoke(commit)

    if current_branch_name == default_branch_name:
        console.print("[bold red]You are on the default branch. Please create a new branch before creating a PR.[/bold red]")
        return

    # Generate PR description using the commit message as context
    with console.status("Generating PR description...", spinner="dots"):
        try:
            pr_description = generate_pr_description(diff_content, commit_message)
        except Exception as e:
            console.print(f"[bold red]Error generating PR description: {e}[/bold red]")
            pr_description = commit_message

    # Show PR description and allow editing
    console.print(Panel(Text(pr_description, style="green"), title="[bold blue]Suggested PR Description[/bold blue]", expand=False))

    if console.input("Use this PR description? (Y/n): ").strip().lower() == 'n':
        console.print("[yellow]You can manually create the PR on GitHub.[/yellow]")
        return

    # Extract the title (first line) for the PR title
    pr_title = commit_message.split('\n')[0]

    # Create the PR
    pr_url = create_pull_request(pr_title, pr_description, base_branch=default_branch_name)

    if pr_url:
        console.print(f"[bold green]Pull request created successfully: {pr_url}[/bold green]")
    else:
        console.print("[bold red]Failed to create pull request.[/bold red]")
