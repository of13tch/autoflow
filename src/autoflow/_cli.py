import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from autoflow._git import (
    check_for_unstaged_changes,
    create_and_checkout_branch,
    get_current_branch,
    get_default_branch,
    get_git_diff,
    git_commit_with_message,
    stage_all_changes,
)
from autoflow._litellm import generate_branch_name, generate_commit_message

console = Console()


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """A CLI to help write good commit messages whilst preserving the flow."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(commit)


@main.command()
# @click.pass_context # No longer needed as ctx is not used
def commit():  # Removed ctx
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

    # Branching logic (if on default branch)
    if default_branch_name and current_branch_name == default_branch_name:
        branch_name = generate_branch_name(diff)
        if branch_name is None:
            console.print("[bold red]Failed to generate branch name. Aborting commit.[/bold red]")
            return

        if console.input(f"[yellow]You are on the default branch ('{current_branch_name}'). Use generated branch name {branch_name}? (y/N): ").strip().lower() == 'y':
            create_and_checkout_branch(branch_name)
        else:
            console.print("[yellow]Proceeding with commit on the default branch.[/yellow]")

    # Staging changes
    # stage_all_changes uses rich for its output
    if not stage_all_changes(): # This will print its own status/errors
        # If staging failed, it would have printed a message.
        # Confirm if user wants to proceed if staging had issues.
        if console.input("[yellow]Staging may have had issues. Proceed anyway? (y/N): ").strip().lower() != 'y':
            console.print("[bold red]Aborting commit due to staging issues.[/bold red]")
            return

    # Diff generation
    with console.status("[bold green]Generating diff...", spinner="dots"):
        diff_content = get_git_diff()

    if diff_content is None:
        console.print("[bold red]Could not get git diff. Exiting.[/bold red]")
        return
    if not diff_content.strip():
        console.print("[yellow]No applicable changes found to commit (lock files might have been excluded or no changes were staged).[/yellow]")
        if check_for_unstaged_changes(): # Check again in case they only staged lock files initially
            console.print("[yellow]However, there are unstaged changes. Did you mean to stage them before running autoflow?[/yellow]")
        return

    # Commit message generation
    # generate_commit_message uses rich for its status and error output
    commit_message = generate_commit_message(diff_content)

    # Handle various outcomes from commit message generation
    if commit_message is None: # Add this check
        console.print("[bold red]Failed to generate commit message. Aborting.[/bold red]")
        return
    if commit_message in ["Error retrieving git diff.", "Error generating commit message.", "Could not generate commit message."]:
        console.print("[bold red]Aborting commit due to errors in message generation.[/bold red]") # Error already printed by called function
        return
    if commit_message == "No applicable changes to commit (lock files might have been excluded).":
        console.print(f"[yellow]{commit_message}[/yellow]")
        return
    # Fallback message for large diff is handled by generate_commit_message printing a warning.
    # We still display it for confirmation.

    console.print(Panel(Text(commit_message, style="green"), title="[bold blue]Suggested Commit Message[/bold blue]", expand=False))

    # Final confirmation
    if console.input("[bold yellow]Commit with this message? (Y/n): ").strip().lower() != 'n':
        if git_commit_with_message(commit_message): # This function uses rich for its output
            # Success message handled by git_commit_with_message
            pass
        else:
            # Error message handled by git_commit_with_message
            pass
    else:
        console.print("[yellow]Commit aborted by user.[/yellow]")
