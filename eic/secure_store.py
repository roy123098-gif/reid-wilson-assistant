import base64
import ctypes
import json
import os
import sys
import tempfile
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parent.parent / "vendor"
if VENDOR_DIR.exists() and str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))

from cryptography.fernet import Fernet, InvalidToken


class EncryptedStoreError(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data):
    buffer = ctypes.create_string_buffer(data)
    value = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    return value, buffer


def _dpapi(operation, data):
    if os.name != "nt":
        return data
    input_blob, input_buffer = _blob(data)
    output_blob = _DataBlob()
    function = getattr(ctypes.windll.crypt32, operation)
    arguments = [ctypes.byref(input_blob), None, None, None, None, 0x1, ctypes.byref(output_blob)]
    if not function(*arguments):
        raise EncryptedStoreError("Windows could not protect or unlock the local encryption key.")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


def _protect_local_key(key):
    if os.name != "nt":
        return key
    return b"dpapi:" + base64.urlsafe_b64encode(_dpapi("CryptProtectData", key))


def _unlock_local_key(stored):
    if stored.startswith(b"dpapi:"):
        if os.name != "nt":
            raise EncryptedStoreError("This profile key is protected for a Windows user and cannot be opened here.")
        protected = base64.urlsafe_b64decode(stored.split(b":", 1)[1])
        return _dpapi("CryptUnprotectData", protected)
    return stored


def _write_key_file(key_file, stored):
    temporary = key_file.with_suffix(".tmp")
    with open(temporary, "wb") as file:
        file.write(stored)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, key_file)
    try:
        os.chmod(key_file, 0o600)
    except OSError:
        pass


def validate_key(value):
    if isinstance(value, str):
        value = value.encode("ascii")
    try:
        Fernet(value)
    except (TypeError, ValueError) as exc:
        raise EncryptedStoreError("PROFILE_ENCRYPTION_KEY is not a valid Fernet key.") from exc
    return value


def get_or_create_key(data_dir, env_name="PROFILE_ENCRYPTION_KEY"):
    configured = os.environ.get(env_name)
    if configured:
        return validate_key(configured.strip())

    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    key_file = data_dir / "profile.key"
    if key_file.exists():
        stored = key_file.read_bytes().strip()
        key = validate_key(_unlock_local_key(stored))
        if os.name == "nt" and not stored.startswith(b"dpapi:"):
            _write_key_file(key_file, _protect_local_key(key))
        return key

    key = Fernet.generate_key()
    try:
        descriptor = os.open(str(key_file), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(_protect_local_key(key))
    except FileExistsError:
        return validate_key(key_file.read_bytes().strip())
    try:
        os.chmod(key_file, 0o600)
    except OSError:
        pass
    return key


def write_encrypted_json(path, payload, key):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    plaintext = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ciphertext = Fernet(validate_key(key)).encrypt(plaintext)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=path.name, suffix=".tmp", delete=False) as file:
            temporary_name = file.name
            file.write(ciphertext)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_name, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def read_encrypted_json(path, key):
    path = Path(path)
    try:
        plaintext = Fernet(validate_key(key)).decrypt(path.read_bytes())
        data = json.loads(plaintext.decode("utf-8"))
    except InvalidToken as exc:
        raise EncryptedStoreError("The encrypted tax profile could not be opened. The key is wrong or the file was changed.") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EncryptedStoreError("The encrypted tax profile is unreadable.") from exc
    if not isinstance(data, dict):
        raise EncryptedStoreError("The encrypted tax profile does not contain a valid profile object.")
    return data


def remove_plaintext_file(path):
    path = Path(path)
    if not path.exists():
        return
    try:
        size = path.stat().st_size
        with open(path, "r+b", buffering=0) as file:
            file.write(os.urandom(size))
            file.flush()
            os.fsync(file.fileno())
    finally:
        path.unlink(missing_ok=True)
