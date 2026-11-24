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


def test_r2_storage_round_trip(monkeypatch) -> None:
    from app.api import files as file_api
    from app.core.config import settings

    class FakeBody:
        def read(self) -> bytes:
            return b"private file bytes"

        def close(self) -> None:
            pass

    class FakeR2:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}

        def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
            self.objects[f"{Bucket}/{Key}"] = Body

        def get_object(self, *, Bucket: str, Key: str) -> dict:
            return {"Body": FakeBodyFor(self.objects[f"{Bucket}/{Key}"])}

        def delete_object(self, *, Bucket: str, Key: str) -> None:
            self.objects.pop(f"{Bucket}/{Key}", None)

    class FakeBodyFor:
        def __init__(self, value: bytes) -> None:
            self.value = value

        def read(self) -> bytes:
            return self.value

        def close(self) -> None:
            pass

    client = FakeR2()
    monkeypatch.setattr(settings, "storage_backend", "r2")
    monkeypatch.setattr(settings, "r2_bucket_name", "quanta-test")
    monkeypatch.setattr(file_api, "_r2_client", lambda: client)

    user_id = __import__("uuid").uuid4()
    filename = "private.txt"
    file_api._write_storage(user_id, filename, b"private file bytes")

    assert file_api._read_storage(user_id, filename) == b"private file bytes"
    assert f"quanta-test/users/{user_id}/{filename}" in client.objects

    file_api._delete_storage(user_id, filename)
    assert not client.objects
