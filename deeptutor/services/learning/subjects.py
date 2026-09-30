"""Subject boundaries for the shared objective learning workflow."""

SUBJECTS = ("Mathematics", "Chinese", "English")
DEFAULT_TOPICS = {"Mathematics": "Algebra", "Chinese": "字詞運用", "English": "Grammar"}
ALIASES = {
    "Chinese": {
        "字詞運用": ("vocabulary", "字詞運用"),
        "修辭": ("rhetoric", "修辭"),
        "閱讀理解": ("reading", "閱讀理解"),
        "阅读理解": ("reading", "閱讀理解"),
    },
    "English": {
        "grammar": ("grammar", "Grammar"),
        "vocabulary": ("vocabulary", "Vocabulary"),
        "reading": ("reading", "Reading comprehension"),
        "reading comprehension": ("reading", "Reading comprehension"),
    },
}


def normalise_subject(value: str) -> str:
    # Lazy import avoids a cycle with the public service exception type.
    from .service import LearningValidationError

    if not isinstance(value, str) or value not in SUBJECTS:
        raise LearningValidationError("subject must be Mathematics, Chinese, or English.")
    return value
