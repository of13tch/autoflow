import os
from typing import Optional

import litellm
from litellm.exceptions import ContextWindowExceededError

from autoflow._exceptions import GenericLLMError, InvalidBranchName, NoDiffContent  # type: ignore

MAX_DIFF_CHARS = 60_000
model = os.getenv("AUTOFLOW_LITELLM_MODEL", "gpt-3.5-turbo")
verbose_str = os.getenv("AUTOFLOW_LITELLM_VERBOSE", "False").lower()
litellm.set_verbose = verbose_str in ("true", "1", "t", "yes")


def generate_commit_message(diff_content: str) -> str:
    """Generates a commit message using litellm based on the diff content."""
    if diff_content is None: # Error occurred in get_git_diff
        return "Error retrieving git diff."
    if not diff_content.strip():
        return "No applicable changes to commit (lock files might have been excluded)."

    if len(diff_content) > MAX_DIFF_CHARS:
        raise ContextWindowExceededError

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
        raise GenericLLMError


def generate_branch_name(diff_content: str) -> Optional[str]:
    """
    Generates a branch name suggestion based on the git diff content using litellm.
    """

    if not diff_content.strip():
        raise NoDiffContent

    if len(diff_content) > MAX_DIFF_CHARS:
        raise ContextWindowExceededError

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

    response = litellm.completion(
        model=model,
        messages=messages,
        temperature=0.5, # Slightly lower temp for more predictable branch names
        max_tokens=50,   # Branch names should be short
    )

    branch_name_suggestion = response.choices[0].message.content.strip()
    # Clean up potential markdown or quotes
    branch_name_suggestion = branch_name_suggestion.replace("`", "").replace("'", "").replace('"', "").strip()

    # Further ensure it's a single, valid-like segment
    if ' ' in branch_name_suggestion or '\\n' in branch_name_suggestion or not branch_name_suggestion:
        raise InvalidBranchName(f"Invalid branch name suggestion: {branch_name_suggestion}")

    return branch_name_suggestion


def generate_pr_description(diff_content: str, commit_message: str = "") -> str:
    """
    Generates a PR description based on the git diff content and commit message.

    Args:
        diff_content: Git diff content showing the changes
        commit_message: Optional commit message to include in the context

    Returns:
        A formatted PR description with summary, changes, and testing instructions
    """
    if not diff_content.strip():
        raise NoDiffContent

    if len(diff_content) > MAX_DIFF_CHARS:
        raise ContextWindowExceededError

    # Build the prompt with context including the commit message if available
    context = f"Commit message: {commit_message}\n\n" if commit_message else ""
    context += f"Code changes:\n{diff_content}"

    system_prompt = """You are an expert at creating detailed, well-structured Pull Request descriptions.
Based on the provided git diff and commit message (if given), create a comprehensive PR description with the following sections:

## Summary
A brief summary of what this PR accomplishes in 1-3 sentences.

## Changes
A bullet-point list of key changes made by this PR. Focus on functionality, not file names.

## Testing Instructions
Steps required to test these changes.

Keep the description professional, concise, and focused on what's important for reviewers to know.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context},
    ]

    try:
        response = litellm.completion(
            model=model,
            messages=messages,
            temperature=0.7,
        )

        if response.choices and response.choices[0].message and response.choices[0].message.content:
            return response.choices[0].message.content.strip()
        else:
            raise GenericLLMError("Failed to generate PR description")
    except Exception as e:
        if isinstance(e, ContextWindowExceededError):
            raise e
        raise GenericLLMError(f"Error generating PR description: {str(e)}")
