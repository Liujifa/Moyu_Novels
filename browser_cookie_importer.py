from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from ctypes import wintypes


class CookieImportError(RuntimeError):
    pass


@dataclass
class ImportedCookieJar:
    browser: str
    cookie_header: str
    cookie_count: int
    profile_path: str


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


class BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.ULONG),
        ("dwInfoVersion", wintypes.ULONG),
        ("pbNonce", ctypes.POINTER(ctypes.c_ubyte)),
        ("cbNonce", wintypes.ULONG),
        ("pbAuthData", ctypes.POINTER(ctypes.c_ubyte)),
        ("cbAuthData", wintypes.ULONG),
        ("pbTag", ctypes.POINTER(ctypes.c_ubyte)),
        ("cbTag", wintypes.ULONG),
        ("pbMacContext", ctypes.POINTER(ctypes.c_ubyte)),
        ("cbMacContext", wintypes.ULONG),
        ("cbAAD", wintypes.ULONG),
        ("cbData", ctypes.c_ulonglong),
        ("dwFlags", wintypes.ULONG),
    ]


crypt32 = ctypes.windll.crypt32
kernel32 = ctypes.windll.kernel32
bcrypt = ctypes.windll.bcrypt

crypt32.CryptUnprotectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),
    ctypes.POINTER(ctypes.c_wchar_p),
    ctypes.POINTER(DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(DATA_BLOB),
]
crypt32.CryptUnprotectData.restype = wintypes.BOOL
kernel32.LocalFree.argtypes = [ctypes.c_void_p]
kernel32.LocalFree.restype = ctypes.c_void_p

bcrypt.BCryptOpenAlgorithmProvider.argtypes = [
    ctypes.POINTER(ctypes.c_void_p),
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.ULONG,
]
bcrypt.BCryptOpenAlgorithmProvider.restype = wintypes.ULONG
bcrypt.BCryptCloseAlgorithmProvider.argtypes = [ctypes.c_void_p, wintypes.ULONG]
bcrypt.BCryptCloseAlgorithmProvider.restype = wintypes.ULONG
bcrypt.BCryptSetProperty.argtypes = [
    ctypes.c_void_p,
    wintypes.LPCWSTR,
    ctypes.c_void_p,
    wintypes.ULONG,
    wintypes.ULONG,
]
bcrypt.BCryptSetProperty.restype = wintypes.ULONG
bcrypt.BCryptGetProperty.argtypes = [
    ctypes.c_void_p,
    wintypes.LPCWSTR,
    ctypes.c_void_p,
    wintypes.ULONG,
    ctypes.POINTER(wintypes.ULONG),
    wintypes.ULONG,
]
bcrypt.BCryptGetProperty.restype = wintypes.ULONG
bcrypt.BCryptGenerateSymmetricKey.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.c_void_p,
    wintypes.ULONG,
    ctypes.c_void_p,
    wintypes.ULONG,
    wintypes.ULONG,
]
bcrypt.BCryptGenerateSymmetricKey.restype = wintypes.ULONG
bcrypt.BCryptDestroyKey.argtypes = [ctypes.c_void_p]
bcrypt.BCryptDestroyKey.restype = wintypes.ULONG
bcrypt.BCryptDecrypt.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.ULONG,
    ctypes.POINTER(BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO),
    ctypes.c_void_p,
    wintypes.ULONG,
    ctypes.c_void_p,
    wintypes.ULONG,
    ctypes.POINTER(wintypes.ULONG),
    wintypes.ULONG,
]
bcrypt.BCryptDecrypt.restype = wintypes.ULONG


STATUS_SUCCESS = 0
BCRYPT_AUTH_MODE_INFO_VERSION = 1
BCRYPT_AES_ALGORITHM = "AES"
BCRYPT_CHAIN_MODE_GCM = "ChainingModeGCM"
BCRYPT_CHAINING_MODE = "ChainingMode"
BCRYPT_OBJECT_LENGTH = "ObjectLength"


CHROMIUM_SOURCES = {
    "edge": {
        "user_data_dir": Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data",
        "state_path": Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data" / "Local State",
    },
    "chrome": {
        "user_data_dir": Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data",
        "state_path": Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Local State",
    },
}

FIREFOX_PROFILES_DIR = Path(os.environ.get("APPDATA", "")) / "Mozilla" / "Firefox" / "Profiles"

TRANSLATIONS = {
    "CN": {
        "locked": "\u6d4f\u89c8\u5668 Cookie \u6570\u636e\u5e93\u6b63\u5728\u4f7f\u7528\u4e2d ({name})\u3002\n\n\u89e3\u51b3\u65b9\u6848\uff1a\u8bf7\u5148\u5173\u95ed\u60a8\u7684\u6d4f\u89c8\u5668 (Chrome, Edge \u6216 Firefox)\uff0c\u4ee5\u4fbf\u4e0b\u8f7d\u5668\u80fd\u591f\u8bfb\u53d6 Cookie\uff0c\u7136\u540e\u91cd\u8bd5\u3002",
        "tag_mismatch": "\u89e3\u5bc6\u5931\u8d25 (BCrypt NTSTATUS 0xc000a002)\u3002\n\n\u8fd9\u5f88\u53ef\u80fd\u662f\u56e0\u4e3a Chrome 127+ \u7684 App-Bound Encryption \u673a\u5236\u5bfc\u81f4\u7684\uff0cMoYu \u65e0\u6cd5\u76f4\u63a5\u89e3\u5bc6\u8fd9\u4e9b Cookie\u3002\n\u89e3\u51b3\u65b9\u6848\uff1a\u8bf7\u4f7f\u7528 Firefox \u6d4f\u89c8\u5668\uff0c\u6216\u8005\u5c06 Cookie \u5bfc\u51fa\u4e3a\u6587\u4ef6\u540e\uff0c\u4f7f\u7528\u201c\u4ece\u6587\u4ef6\u5bfc\u5165\u201d\u529f\u80fd\u3002",
        "file_not_found": "Cookie \u6587\u4ef6\u672a\u627e\u5230: {path}",
        "read_failed": "\u8bfb\u53d6 Cookie \u6587\u4ef6\u5931\u8d25: {error}",
        "no_cookies": "\u5728\u9009\u62e9\u7684\u6587\u4ef6\u4e2d\u672a\u627e\u5230 {domain} \u7684 Cookie\u3002",
        "unsupported": "\u4e0d\u652f\u6301\u7684\u6d4f\u89c8\u5668: {browser}",
        "master_key_locked": "\u6d4f\u89c8\u5668\u5143\u6570\u636e\u6587\u4ef6\u5df2\u9501\u5b9a ({name})\u3002\n\n\u89e3\u51b3\u65b9\u6848\uff1a\u8bf7\u5148\u5173\u95ed\u60a8\u7684\u6d4f\u89c8\u5668 (Chrome \u6216 Edge)\u3002",
    },
    "EN": {
        "locked": "The browser cookie database is currently in use ({name}).\n\nSolution: Please CLOSE your web browser (Chrome, Edge, or Firefox) so the downloader can access the cookies, then try again.",
        "tag_mismatch": "Decryption failed (BCrypt NTSTATUS 0xc000a002).\n\nThis is likely due to Chrome 127+ App-Bound Encryption. MoYu cannot decrypt these directly.\nWorkaround: Use Firefox, or export cookies to a file and use 'Import from file'.",
        "file_not_found": "Cookie file not found: {path}",
        "read_failed": "Failed to read cookie file: {error}",
        "no_cookies": "No cookies for {domain} were found in the selected file.",
        "unsupported": "Unsupported browser: {browser}",
        "master_key_locked": "The browser metadata file is locked ({name}).\n\nSolution: Please CLOSE your web browser (Chrome or Edge).",
    }
}


def _check_status(status: int, action: str, details: str = "", language: str = "CN") -> None:
    if status != STATUS_SUCCESS:
        error_msg = f"{action} failed with NTSTATUS 0x{status:08x}"
        if status == 0xc000a002:  # STATUS_AUTH_TAG_MISMATCH
            trans = TRANSLATIONS.get(language, TRANSLATIONS["EN"])
            error_msg = trans["tag_mismatch"]
        if details:
            error_msg += f"\nDetails: {details}"
        raise CookieImportError(error_msg)


def _dpapi_unprotect(data: bytes) -> bytes:
    if not data:
        return b""
    input_buffer = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_byte)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _aes_gcm_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, tag: bytes, language: str = "CN") -> bytes:
    algorithm = ctypes.c_void_p()
    key_handle = ctypes.c_void_p()
    key_object = None
    try:
        _check_status(
            bcrypt.BCryptOpenAlgorithmProvider(ctypes.byref(algorithm), BCRYPT_AES_ALGORITHM, None, 0),
            "BCryptOpenAlgorithmProvider",
            language=language,
        )

        chaining_mode = ctypes.create_unicode_buffer(BCRYPT_CHAIN_MODE_GCM)
        _check_status(
            bcrypt.BCryptSetProperty(
                algorithm,
                BCRYPT_CHAINING_MODE,
                ctypes.cast(chaining_mode, ctypes.c_void_p),
                ctypes.sizeof(chaining_mode),
                0,
            ),
            "BCryptSetProperty",
            language=language,
        )

        object_length = wintypes.ULONG()
        result_length = wintypes.ULONG()
        _check_status(
            bcrypt.BCryptGetProperty(
                algorithm,
                BCRYPT_OBJECT_LENGTH,
                ctypes.byref(object_length),
                ctypes.sizeof(object_length),
                ctypes.byref(result_length),
                0,
            ),
            "BCryptGetProperty",
            language=language,
        )

        key_object = ctypes.create_string_buffer(object_length.value)
        key_buffer = ctypes.create_string_buffer(key, len(key))
        _check_status(
            bcrypt.BCryptGenerateSymmetricKey(
                algorithm,
                ctypes.byref(key_handle),
                key_object,
                object_length.value,
                key_buffer,
                len(key),
                0,
            ),
            "BCryptGenerateSymmetricKey",
            language=language,
        )

        nonce_buffer = ctypes.create_string_buffer(nonce, len(nonce))
        tag_buffer = ctypes.create_string_buffer(tag, len(tag))
        cipher_buffer = ctypes.create_string_buffer(ciphertext, len(ciphertext))

        auth_info = BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO()
        auth_info.cbSize = ctypes.sizeof(BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO)
        auth_info.dwInfoVersion = BCRYPT_AUTH_MODE_INFO_VERSION
        auth_info.pbNonce = ctypes.cast(nonce_buffer, ctypes.POINTER(ctypes.c_ubyte))
        auth_info.cbNonce = len(nonce)
        auth_info.pbTag = ctypes.cast(tag_buffer, ctypes.POINTER(ctypes.c_ubyte))
        auth_info.cbTag = len(tag)

        output_length = wintypes.ULONG()
        _check_status(
            bcrypt.BCryptDecrypt(
                key_handle,
                cipher_buffer,
                len(ciphertext),
                ctypes.byref(auth_info),
                None,
                0,
                None,
                0,
                ctypes.byref(output_length),
                0,
            ),
            "BCryptDecrypt(size)",
            language=language,
        )

        output_buffer = ctypes.create_string_buffer(output_length.value)
        _check_status(
            bcrypt.BCryptDecrypt(
                key_handle,
                cipher_buffer,
                len(ciphertext),
                ctypes.byref(auth_info),
                None,
                0,
                output_buffer,
                output_length.value,
                ctypes.byref(output_length),
                0,
            ),
            "BCryptDecrypt",
            "",
            language
        )
        return output_buffer.raw[: output_length.value]
    finally:
        if key_handle:
            bcrypt.BCryptDestroyKey(key_handle)
        if algorithm:
            bcrypt.BCryptCloseAlgorithmProvider(algorithm, 0)


def _decrypt_chromium_value(encrypted_value: bytes, master_key: bytes, language: str = "CN", host_key: str = "") -> str:
    if not encrypted_value:
        return ""
    if encrypted_value.startswith(b"v20"):
        # 应用绑定加密不能使用旧版主密钥解密，应直接说明导出文件的替代路径。
        trans = TRANSLATIONS.get(language, TRANSLATIONS["EN"])
        raise CookieImportError(trans["tag_mismatch"])
    if encrypted_value.startswith((b"v10", b"v11")):
        if len(encrypted_value) < 31:
            raise CookieImportError("Cookie 加密数据不完整。")
        nonce = encrypted_value[3:15]
        ciphertext = encrypted_value[15:-16]
        tag = encrypted_value[-16:]
        plain = _aes_gcm_decrypt(master_key, nonce, ciphertext, tag, language)
        # 新版 Chromium 在明文前加上域名哈希，不能把这段二进制数据作为 Cookie 值。
        if host_key and plain.startswith(hashlib.sha256(host_key.encode("utf-8")).digest()):
            plain = plain[32:]
        return plain.decode("utf-8", errors="strict")
    return _dpapi_unprotect(encrypted_value).decode("utf-8", errors="ignore")


def _copy_sqlite_db(db_path: Path, language: str = "CN") -> str:
    temp_dir = tempfile.mkdtemp(prefix="reader_cookie_")
    temp_path = Path(temp_dir) / db_path.name
    try:
        shutil.copy2(db_path, temp_path)
    except (PermissionError, OSError) as exc:
        trans = TRANSLATIONS.get(language, TRANSLATIONS["EN"])
        raise CookieImportError(trans["locked"].format(name=db_path.name)) from exc
    return str(temp_path)


def _query_sqlite_rows(db_path: Path, query: str, params: tuple, language: str = "CN") -> list[tuple]:
    sqlite_uri = f"file:{db_path.as_posix()}?mode=ro&immutable=1"
    try:
        with sqlite3.connect(sqlite_uri, uri=True) as conn:
            return conn.execute(query, params).fetchall()
    except (sqlite3.Error, PermissionError, OSError):
        temp_db = _copy_sqlite_db(db_path, language)
        try:
            with sqlite3.connect(temp_db) as conn:
                return conn.execute(query, params).fetchall()
        finally:
            shutil.rmtree(Path(temp_db).parent, ignore_errors=True)


def _load_chromium_master_key(state_path: Path, language: str = "CN") -> bytes:
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (PermissionError, OSError) as exc:
        trans = TRANSLATIONS.get(language, TRANSLATIONS["EN"])
        raise CookieImportError(trans["master_key_locked"].format(name=state_path.name)) from exc
    encrypted_key = base64.b64decode(state["os_crypt"]["encrypted_key"])
    if encrypted_key.startswith(b"DPAPI"):
        encrypted_key = encrypted_key[5:]
    try:
        return _dpapi_unprotect(encrypted_key)
    except OSError as exc:
        raise CookieImportError(
            "Current browser master key could not be decrypted in this Windows session."
        ) from exc


def _iter_chromium_cookie_dbs(user_data_dir: Path):
    for profile in sorted(user_data_dir.iterdir()):
        if not profile.is_dir():
            continue
        if profile.name != "Default" and not profile.name.startswith("Profile"):
            continue
        for candidate in (profile / "Network" / "Cookies", profile / "Cookies"):
            if candidate.exists():
                yield profile, candidate
                break


def _build_cookie_header(cookie_pairs: dict[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookie_pairs.items() if value)


def _domain_matches(cookie_domain: str, hostname: str, host_only: bool = False) -> bool:
    if not isinstance(cookie_domain, str):
        return False
    domain = cookie_domain.lstrip(".").lower().rstrip(".")
    hostname = hostname.lower().rstrip(".")
    return bool(domain and (hostname == domain or (not host_only and hostname.endswith("." + domain))))


def _cookie_hosts(hostname: str) -> list[str]:
    parts = hostname.lower().rstrip(".").split(".")
    return [prefix + ".".join(parts[index:])
            for index in range(max(1, len(parts) - 1)) for prefix in ("", ".")]


def import_chromium_cookies(browser: str, domain: str, language: str = "CN") -> ImportedCookieJar:
    source = CHROMIUM_SOURCES.get(browser)
    if not source:
        trans = TRANSLATIONS.get(language, TRANSLATIONS["EN"])
        raise CookieImportError(trans["unsupported"].format(browser=browser))

    user_data_dir = source["user_data_dir"]
    state_path = source["state_path"]
    if not state_path.exists() or not user_data_dir.exists():
        trans = TRANSLATIONS.get(language, TRANSLATIONS["EN"])
        raise CookieImportError(trans["unsupported"].format(browser=browser))

    master_key = _load_chromium_master_key(state_path, language)
    collected: dict[str, str] = {}
    profile_path = ""

    for profile, db_path in _iter_chromium_cookie_dbs(user_data_dir):
        hosts = _cookie_hosts(domain)
        rows = _query_sqlite_rows(
            db_path,
            f"""
            SELECT host_key, name, value, encrypted_value
            FROM cookies
            WHERE host_key IN ({','.join('?' for _ in hosts)})
            ORDER BY LENGTH(host_key) DESC, last_access_utc DESC
            """,
            tuple(hosts),
            language,
        )
        if not rows:
            continue

        for host_key, name, value, encrypted_value in rows:
            if not _domain_matches(host_key, domain, not host_key.startswith(".")):
                continue
            if name in collected:
                continue
            plain_value = value or _decrypt_chromium_value(encrypted_value, master_key, language, host_key)
            if plain_value:
                collected[name] = plain_value

        if collected:
            profile_path = str(profile)
            break

    if not collected:
        raise CookieImportError(f"No {domain} cookies were found in {browser}")

    return ImportedCookieJar(
        browser=browser,
        cookie_header=_build_cookie_header(collected),
        cookie_count=len(collected),
        profile_path=profile_path,
    )


def import_firefox_cookies(domain: str, language: str = "CN") -> ImportedCookieJar:
    if not FIREFOX_PROFILES_DIR.exists():
        raise CookieImportError("Firefox profiles were not found on this machine")

    collected: dict[str, str] = {}
    profile_path = ""
    for profile in sorted(FIREFOX_PROFILES_DIR.iterdir()):
        if not profile.is_dir():
            continue
        db_path = profile / "cookies.sqlite"
        if not db_path.exists():
            continue

        hosts = _cookie_hosts(domain)
        rows = _query_sqlite_rows(
            db_path,
            f"""
            SELECT host, name, value
            FROM moz_cookies
            WHERE host IN ({','.join('?' for _ in hosts)})
            ORDER BY LENGTH(host) DESC, lastAccessed DESC
            """,
            tuple(hosts),
            language,
        )
        if not rows:
            continue

        for host, name, value in rows:
            if not _domain_matches(host, domain, not host.startswith(".")):
                continue
            if name not in collected and value:
                collected[name] = value

        if collected:
            profile_path = str(profile)
            break

    if not collected:
        raise CookieImportError(f"No {domain} cookies were found in Firefox")

    return ImportedCookieJar(
        browser="firefox",
        cookie_header=_build_cookie_header(collected),
        cookie_count=len(collected),
        profile_path=profile_path,
    )


def import_browser_cookies(browser: str, domain: str, language: str = "CN") -> ImportedCookieJar:
    browser = (browser or "").strip().lower()
    if browser in CHROMIUM_SOURCES:
        return import_chromium_cookies(browser, domain, language)
    if browser == "firefox":
        return import_firefox_cookies(domain, language)
    trans = TRANSLATIONS.get(language, TRANSLATIONS["EN"])
    raise CookieImportError(trans["unsupported"].format(browser=browser))


def import_cookies_from_file(file_path: str, domain: str, language: str = "CN") -> ImportedCookieJar:
    path = Path(file_path)
    if not path.exists():
        trans = TRANSLATIONS.get(language, TRANSLATIONS["EN"])
        raise CookieImportError(trans["file_not_found"].format(path=file_path))

    collected: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        trans = TRANSLATIONS.get(language, TRANSLATIONS["EN"])
        raise CookieImportError(trans["read_failed"].format(error=e))

    # 保留 HttpOnly 行与父域 Cookie，按域名边界匹配，不能误收相似域名。
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            data = data.get("cookies", [])
        if isinstance(data, list):
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                cookie_domain = entry.get("domain", "")
                expiry = entry.get("expirationDate", entry.get("expires", 0))
                try:
                    if float(expiry or 0) > 0 and float(expiry) <= time.time():
                        continue
                except (TypeError, ValueError):
                    continue
                if _domain_matches(cookie_domain, domain, entry.get("hostOnly") is True):
                    name = entry.get("name")
                    value = entry.get("value")
                    if isinstance(name, str) and isinstance(value, str) and name and value:
                        collected[name] = value
    except (json.JSONDecodeError, TypeError):
        # 非 JSON 时兼容 Netscape 文件和手工复制的 Cookie 请求头。
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("#HttpOnly_"):
                line = line[len("#HttpOnly_"):]
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                cookie_domain = parts[0]
                try:
                    expiry = float(parts[4])
                except ValueError:
                    continue
                if expiry > 0 and expiry <= time.time():
                    continue
                if _domain_matches(cookie_domain, domain, parts[1].upper() != "TRUE"):
                    name = parts[5]
                    value = parts[6]
                    if name and value:
                        collected[name] = value
            elif "=" in line:
                # Fallback for simple key=value lines
                if ";" in line:
                    for pair in line.split(";"):
                        if "=" in pair:
                            name, value = pair.strip().split("=", 1)
                            collected[name] = value
                else:
                    name, value = line.split("=", 1)
                    collected[name.strip()] = value.strip()

    if not collected:
        trans = TRANSLATIONS.get(language, TRANSLATIONS["EN"])
        raise CookieImportError(trans["no_cookies"].format(domain=domain))

    return ImportedCookieJar(
        browser="file",
        cookie_header=_build_cookie_header(collected),
        cookie_count=len(collected),
        profile_path=str(path),
    )
