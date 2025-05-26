import click

from autoflow.git import (
    check_for_unstaged_changes,
    create_and_checkout_branch,
    get_current_branch,
    get_default_branch,
    get_git_diff,
    git_commit_with_message,
    stage_all_changes,
)
from autoflow.litellm import generate_commit_message


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """A CLI to help write good commit messages whilst preserving the flow."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(commit)

@main.command()
@click.pass_context
def commit(ctx):
    """Manages branching, staging, and committing changes with an AI-generated message."""
    current_branch_name = get_current_branch()
    if not current_branch_name:
        click.echo(click.style("Could not determine current branch. Exiting.", fg="red"))
        return

    default_branch_name = get_default_branch()

    if default_branch_name and current_branch_name == default_branch_name:
        if click.confirm(click.style(f"You are on the default branch (\'{current_branch_name}\'). Do you want to create a new branch?", fg="yellow"), default=True):
            new_branch_name_input = click.prompt(click.style("Enter the name for the new branch", fg="cyan"))
            if not new_branch_name_input.strip():
                click.echo(click.style("Branch name cannot be empty. Aborting commit.", fg="red"))
                return
            if not create_and_checkout_branch(new_branch_name_input):
                click.echo(click.style("Failed to create new branch. Aborting commit.", fg="red"))
                return
        else:
            click.echo(click.style("Proceeding with commit on the default branch.", fg="yellow"))

    if check_for_unstaged_changes():
        if click.confirm(click.style("You have unstaged changes. Do you want to stage them all?", fg="yellow"), default=True):
            if not stage_all_changes():
                click.echo(click.style("Failed to stage changes. Please stage them manually or resolve issues.", fg="red"))
                if not click.confirm("Proceed without staging all changes?", default=False):
                    return
        else:
            click.echo(click.style("Proceeding without staging new changes. Only previously staged changes will be committed.", fg="yellow"))

    diff_content = get_git_diff()
    if diff_content is None: # Error in get_git_diff
        click.echo(click.style("Could not get git diff. Exiting.", fg="red"))
        return
    if not diff_content:
        click.echo("No staged changes found to commit.")
        if check_for_unstaged_changes():
            click.echo(click.style("However, there are unstaged changes. Did you mean to stage them?", fg="yellow"))
        return

    click.echo("Generating commit message...")
    commit_message = generate_commit_message(diff_content)
    
    if commit_message == "Error retrieving git diff." or commit_message == "Error generating commit message.":
         # Error already printed by the generating function
        return
    if commit_message == "No applicable changes to commit (lock files might have been excluded).":
        click.echo(commit_message)
        return

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
