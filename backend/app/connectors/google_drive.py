"""The Google Drive connector (docs/development/google-drive.md).

First sync: take a change token, then list every supported file the
account can read (a complete listing, so files that left the account leave
retrieval). Later syncs read only the Drive changes since the saved token.

Permissions come from Drive itself, file by file. When Drive does not tell
(the account cannot see a file's sharing), only the connected account is
granted: fail closed, as everywhere else (ADR-003).

The refresh token is opened by the worker from the sealed store (ADR-007)
and lives only in this object's memory; access tokens are never stored.
"""

import logging
from datetime import datetime

import httpx

from app.connectors.base import (
    ChangeSet,
    ConnectionContext,
    ConnectorAuthError,
    ConnectorError,
    SourceItem,
    register_connector,
)
from app.core.config import settings
from app.services.document_permission_service import (
    InvalidPermissionError,
    SourcePermission,
)
from app.services.text_extraction import MAX_FILE_BYTES, extract_text


logger = logging.getLogger("eka.google_drive")

API_URL = "https://www.googleapis.com/drive/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"

GOOGLE_DOC = "application/vnd.google-apps.document"
GOOGLE_SLIDES = "application/vnd.google-apps.presentation"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# Google formats are exported as text; files are downloaded and read by
# the same extraction as uploads. Sheets and Excel are tabular: they are
# answered by queries (ADR-006), so they are not listed here.
EXPORTED = (GOOGLE_DOC, GOOGLE_SLIDES)
DOWNLOADED = ("application/pdf", DOCX, "text/plain", "text/markdown")
SUPPORTED = EXPORTED + DOWNLOADED

FILE_FIELDS = (
    "id,name,mimeType,md5Checksum,version,modifiedTime,size,trashed,"
    "driveId,permissions(type,role,emailAddress,domain,deleted)"
)
PAGE_SIZE = 1000

ROLES = {
    "owner": "owner",
    "organizer": "writer",
    "fileOrganizer": "writer",
    "writer": "writer",
    "commenter": "commenter",
    "reader": "reader",
}

# Answers that mean "try again later" rather than "this file is broken".
RATE_LIMIT_REASONS = ("rateLimitExceeded", "userRateLimitExceeded")


class ItemNotReadable(Exception):
    """This file cannot be read (gone, too large, export refused).

    Not a ConnectorError: it is about one file, and retrying the whole
    sync would not change it.
    """


def http_client() -> httpx.Client:
    return httpx.Client(timeout=30.0)


def _reason(response: httpx.Response) -> str:
    try:
        error = response.json().get("error", {})
    except ValueError:
        return ""
    if isinstance(error, str):
        return error
    errors = error.get("errors") or [{}]
    return str(errors[0].get("reason") or error.get("status") or "")


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class DriveClient:
    def __init__(self, refresh_token: str, http: httpx.Client):
        self.refresh_token = refresh_token
        self.http = http
        self._access_token: str | None = None

    def __repr__(self) -> str:
        return "DriveClient(<hidden>)"

    def _refresh(self) -> None:
        if not (
            settings.GOOGLE_OAUTH_CLIENT_ID
            and settings.GOOGLE_OAUTH_CLIENT_SECRET
        ):
            raise ConnectorError(
                "Google sign-in is not configured on this server"
            )
        try:
            response = self.http.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                    "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                },
            )
        except httpx.HTTPError as exc:
            raise ConnectorError(f"Google unreachable: {type(exc).__name__}")

        if response.status_code in (400, 401):
            # invalid_grant: access was removed in the Google account, or
            # the authorization expired. An admin must connect again.
            raise ConnectorAuthError(
                f"Google refused the authorization ({_reason(response)})"
            )
        if response.status_code != 200:
            raise ConnectorError(f"Google sign-in answered {response.status_code}")

        self._access_token = response.json()["access_token"]

    def get(self, path: str, params: dict | None = None) -> httpx.Response:
        for attempt in (1, 2):
            if self._access_token is None:
                self._refresh()
            try:
                response = self.http.get(
                    f"{API_URL}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {self._access_token}"},
                )
            except httpx.HTTPError as exc:
                raise ConnectorError(
                    f"Google Drive unreachable: {type(exc).__name__}"
                )
            if response.status_code == 401 and attempt == 1:
                # The access token expired: refresh once.
                self._access_token = None
                continue
            break

        status = response.status_code
        if status == 200:
            return response
        if status == 401:
            raise ConnectorAuthError("Google Drive refused the access token")
        reason = _reason(response)
        if status == 429 or status >= 500 or reason in RATE_LIMIT_REASONS:
            raise ConnectorError(f"Google Drive busy ({status} {reason})")
        if status in (403, 404):
            raise ItemNotReadable(f"Google Drive answered {status} {reason}")
        raise ConnectorError(f"Google Drive answered {status} {reason}")


class GoogleDriveConnector:
    def __init__(self, context: ConnectionContext, http: httpx.Client | None = None):
        self.context = context
        self.http = http or http_client()
        refresh_token = (context.credentials or {}).get("refresh_token")
        self.client = DriveClient(refresh_token, self.http) if refresh_token else None
        self._account_email: str | None = None
        self._sizes: dict[str, int] = {}

    def close(self) -> None:
        self.http.close()

    def _drive(self) -> DriveClient:
        if self.client is None:
            raise ConnectorAuthError(
                "this connection has no Google authorization; connect the "
                "account again"
            )
        return self.client

    def account_email(self) -> str:
        if self._account_email is None:
            about = self._drive().get(
                "/about", {"fields": "user(emailAddress)"}
            ).json()
            self._account_email = about["user"]["emailAddress"].lower()
        return self._account_email

    # Permissions

    def _shared_drive_permissions(self, file_id: str) -> list | None:
        found, token = [], None
        while True:
            params = {
                "supportsAllDrives": "true",
                "pageSize": 100,
                "fields": (
                    "nextPageToken,"
                    "permissions(type,role,emailAddress,domain,deleted)"
                ),
            }
            if token:
                params["pageToken"] = token
            try:
                data = self._drive().get(
                    f"/files/{file_id}/permissions", params
                ).json()
            except ItemNotReadable:
                return None
            found.extend(data.get("permissions", []))
            token = data.get("nextPageToken")
            if not token:
                return found

    def _permissions(self, file: dict) -> tuple[SourcePermission, ...]:
        raw = file.get("permissions")
        if raw is None and file.get("driveId"):
            raw = self._shared_drive_permissions(file["id"])
        if raw is None:
            # Drive does not show this file's sharing to the account: only
            # the account itself is known to read it.
            return (SourcePermission("user", self.account_email(), "reader"),)

        permissions = []
        for entry in raw:
            role = ROLES.get(entry.get("role", ""))
            if entry.get("deleted") or role is None:
                continue
            kind = entry.get("type")
            if kind in ("user", "group"):
                candidate = SourcePermission(kind, entry.get("emailAddress", ""), role)
            elif kind == "domain":
                candidate = SourcePermission("domain", entry.get("domain", ""), role)
            elif kind == "anyone":
                candidate = SourcePermission("anyone", "", role)
            else:
                continue
            try:
                permissions.append(candidate.normalized())
            except InvalidPermissionError:
                continue
        return tuple(permissions)

    # Listing

    def _item(self, file: dict) -> SourceItem:
        if file.get("size"):
            self._sizes[file["id"]] = int(file["size"])
        return SourceItem(
            external_id=file["id"],
            title=file.get("name") or file["id"],
            mime_type=file.get("mimeType"),
            revision=file.get("md5Checksum") or file.get("version"),
            modified_at=_parse_time(file.get("modifiedTime")),
            permissions=self._permissions(file),
        )

    def _full_listing(self) -> ChangeSet:
        # Take the change token first: whatever changes during the listing
        # is read again by the next sync.
        start = self._drive().get(
            "/changes/startPageToken", {"supportsAllDrives": "true"}
        ).json()["startPageToken"]

        types = " or ".join(f"mimeType = '{mime}'" for mime in SUPPORTED)
        items, token, incomplete = [], None, False
        while True:
            params = {
                "q": f"trashed = false and ({types})",
                "fields": f"nextPageToken,incompleteSearch,files({FILE_FIELDS})",
                "pageSize": PAGE_SIZE,
                "corpora": "allDrives",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if token:
                params["pageToken"] = token
            data = self._drive().get("/files", params).json()
            incomplete = incomplete or bool(data.get("incompleteSearch"))
            items.extend(self._item(file) for file in data.get("files", []))
            token = data.get("nextPageToken")
            if not token:
                break

        # An incomplete answer must not remove what it did not list.
        return ChangeSet(changed=tuple(items), cursor=start, complete=not incomplete)

    def _changes_since(self, cursor: str) -> ChangeSet:
        changed: dict[str, SourceItem] = {}
        removed: dict[str, None] = {}
        token = cursor
        while True:
            data = self._drive().get(
                "/changes",
                {
                    "pageToken": token,
                    "fields": (
                        "nextPageToken,newStartPageToken,"
                        f"changes(changeType,removed,fileId,file({FILE_FIELDS}))"
                    ),
                    "pageSize": PAGE_SIZE,
                    "includeRemoved": "true",
                    "supportsAllDrives": "true",
                    "includeItemsFromAllDrives": "true",
                },
            ).json()

            for change in data.get("changes", []):
                if change.get("changeType", "file") != "file":
                    continue
                file_id, file = change.get("fileId"), change.get("file")
                if not file_id:
                    continue
                if (
                    change.get("removed")
                    or file is None
                    or file.get("trashed")
                    or file.get("mimeType") not in SUPPORTED
                ):
                    changed.pop(file_id, None)
                    removed[file_id] = None
                else:
                    removed.pop(file_id, None)
                    changed[file_id] = self._item(file)

            if data.get("newStartPageToken"):
                return ChangeSet(
                    changed=tuple(changed.values()),
                    removed=tuple(removed),
                    cursor=data["newStartPageToken"],
                )
            token = data["nextPageToken"]

    def list_changes(self, cursor: str | None) -> ChangeSet:
        if cursor is None:
            return self._full_listing()
        return self._changes_since(cursor)

    # Content

    def fetch_text(self, item: SourceItem) -> str:
        if item.mime_type in EXPORTED:
            response = self._drive().get(
                f"/files/{item.external_id}/export", {"mimeType": "text/plain"}
            )
            return response.content.decode("utf-8-sig", errors="replace")

        if self._sizes.get(item.external_id, 0) > MAX_FILE_BYTES:
            raise ItemNotReadable("the file is larger than 20 MB")
        response = self._drive().get(
            f"/files/{item.external_id}",
            {"alt": "media", "supportsAllDrives": "true"},
        )
        _, text = extract_text(response.content)
        return text


@register_connector("google_drive")
def build(context: ConnectionContext) -> GoogleDriveConnector:
    return GoogleDriveConnector(context)
