class NoDiffContent(Exception):
    """Raised when there is no diff content to process."""
    def __init__(self, message="No diff content available."):
        super().__init__(message)


class ContextWindowExceededError(Exception):
    """Raised when the diff content exceeds the context window of the LLM."""
    def __init__(self, message="Diff content exceeds the context window of the LLM."):
        super().__init__(message)


class GenericLLMError(Exception):
    """Raised for generic errors related to LLM operations."""
    def __init__(self, message="An error occurred with the LLM operation."):
        super().__init__(message)


class InvalidBranchName(Exception):
    """Raised when the generated branch name is invalid."""
    def __init__(self, message="The generated branch name is invalid."):
        super().__init__(message)
