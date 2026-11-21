"""Outlook file ingestion (W1): .eml -> mail- evidence / proposals, .ics -> cal- reminders."""


def import_files(files: list) -> dict:
    """files: list of (filename, bytes). Return {"created": [...], "drafts": [...], "reminders": [...]}. Timer: `outlook_import`."""
    raise NotImplementedError("W1: implement core/outlook.import_files")
