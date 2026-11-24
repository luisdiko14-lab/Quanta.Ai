import pytest
from fastapi import HTTPException

from app.api.files import _extract_text, _safe_filename, _validate_file


def test_safe_filename_removes_path_components() -> None:
    assert _safe_filename("../../private notes.txt") == "private notes.txt"


def test_utf8_text_upload_is_validated_and_extractable() -> None:
    data = "Quanta AI file context".encode("utf-8")

    extension, media_type = _validate_file("notes.txt", data)

    assert extension == ".txt"
    assert media_type.startswith("text/")
    assert _extract_text(extension, data) == "Quanta AI file context"


def test_invalid_pdf_signature_is_rejected() -> None:
    with pytest.raises(HTTPException) as error:
        _validate_file("document.pdf", b"not a PDF")

    assert error.value.status_code == 400


def test_unknown_extensions_are_rejected() -> None:
    with pytest.raises(HTTPException) as error:
        _validate_file("payload.exe", b"MZ")

    assert error.value.status_code == 415
