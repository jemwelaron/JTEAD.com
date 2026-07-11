# Lightweight, dependency-free file-type sniffing by magic bytes/signature,
# so upload validation doesn't rely solely on the (trivially spoofable)
# filename extension. Deliberately not using python-magic here since that
# needs the system libmagic library installed, which adds a deployment
# dependency we don't need for this small, known set of file types.

import os

SIGNATURES = {
    "pdf": [b"%PDF-"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpeg": [b"\xff\xd8\xff"],
    "jpg": [b"\xff\xd8\xff"],
    "tiff": [b"II*\x00", b"MM\x00*"],
    "tif": [b"II*\x00", b"MM\x00*"],
    # .docx/.xlsx are ZIP containers (Office Open XML)
    "docx": [b"PK\x03\x04", b"PK\x05\x06"],
    "xlsx": [b"PK\x03\x04", b"PK\x05\x06"],
    "zip": [b"PK\x03\x04", b"PK\x05\x06"],
    # legacy .doc/.xls are OLE2 Compound File Binary Format
    "doc": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    "xls": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    "rtf": [b"{\\rtf1"],
}

# No reliable magic bytes for plain text formats — instead, reject anything
# that doesn't decode as UTF-8 text (catches a renamed binary/executable).
TEXT_EXTENSIONS = {"csv", "txt", "json"}

SNIFF_BYTES = 16


def file_extension_ok(filename, allowed_extensions):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


def file_size_ok(file_storage, max_bytes):
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    return size <= max_bytes


def file_content_matches_extension(file_storage, extension):
    extension = extension.lower()
    file_storage.stream.seek(0)
    header = file_storage.stream.read(SNIFF_BYTES)
    file_storage.stream.seek(0)

    if extension in SIGNATURES:
        return any(header.startswith(sig) for sig in SIGNATURES[extension])

    if extension in TEXT_EXTENSIONS:
        try:
            header.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False

    # No signature defined for this extension — the extension whitelist
    # already covers it, so don't block on a content check we can't do.
    return True
