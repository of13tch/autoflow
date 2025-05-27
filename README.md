# autoflow
AutoFlow is a simple CLI to help write good commit messages and PR descriptions whilst preserving the flow

## Features

- **AI-Generated Commit Messages**: Uses LiteLLM to generate descriptive, conventional commit messages based on your code changes
- **Automatic Branch Creation**: If you're on a default branch, AutoFlow offers to create a new branch with an AI-generated name based on your changes
- **Smart Staging**: Automatically stages all relevant files, excluding common lock files
- **PR Creation**: One-step process to commit changes and create a PR with a well-structured description

## Installation

```bash
pip install autoflow
```

## Configuration

AutoFlow uses the following environment variables for configuration:

```bash
# Required for PR creation
export GITHUB_TOKEN=your_github_token

# Optional LiteLLM configuration
export AUTOFLOW_LITELLM_MODEL=gpt-3.5-turbo  # Default model
export AUTOFLOW_LITELLM_VERBOSE=false        # Set to true for verbose output
```

## Usage

### Generate a commit message and commit changes

```bash
flow commit
# or simply
flow
```

### Generate a commit message, commit changes, and create a PR

```bash
flow pr
```

## Requirements

- Python 3.10+
- Git
- GitHub account (for PR creation)
