import argparse
import os
import re
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:  # pragma: no cover - optional dependency until installed
    InstalledAppFlow = None

try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
except ImportError:  # pragma: no cover - optional dependency until installed
    build = None
    MediaFileUpload = None

SCOPES = ["https://www.googleapis.com/auth/youtube"]
DEFAULT_CLIENT_SECRETS = "client_secret.json"
DEFAULT_TOKEN_FILE = "youtube_token.json"
DEFAULT_DESCRIPTION = "#asmongold #asmongold翻譯"
DEFAULT_PLAYLIST_ID = "PL07RseMmSVbOMpozStIGt-zoOw6XslJGy"
DEFAULT_HASHTAGS = ["asmongold", "asmongold翻譯"]
DEFAULT_TAGS = ["asmongold", "asmongold翻譯"]
DEFAULT_VIDEO_FILENAME = "result.mp4"
DEFAULT_THUMBNAIL_FILENAME = "thumbnail.jpg"


def clean_filename(text):
    text = re.sub(r"#\S+", "", text)
    return re.sub(r'[\\/*?:"<>|]', "", text).strip()


def parse_publish_time(value):
    if value is None:
        return None

    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    publish_time = datetime.fromisoformat(text)
    if publish_time.tzinfo is None:
        publish_time = publish_time.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return publish_time.astimezone(timezone.utc)


def to_rfc3339(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _save_credentials(creds, token_file):
    if token_file:
        with open(token_file, "w", encoding="utf-8") as token_handle:
            token_handle.write(creds.to_json())


def load_credentials(client_secrets_file, token_file, use_console=False):
    if InstalledAppFlow is None:
        raise RuntimeError(
            "google-auth-oauthlib is required. Install dependencies with `uv sync`."
        )

    creds = None
    if token_file and os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(creds, token_file)

    if not creds or not creds.valid:
        if not client_secrets_file or not os.path.exists(client_secrets_file):
            raise FileNotFoundError(
                f"Client secrets file not found: {client_secrets_file}"
            )
        flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
        if use_console:
            creds = flow.run_local_server(
                port=0,
                open_browser=False,
                authorization_prompt_message=(
                    "Please open this URL to authorize this application:\n{url}\n"
                ),
            )
        else:
            creds = flow.run_local_server(port=0)

        _save_credentials(creds, token_file)

    return creds


def normalize_hashtags(hashtags):
    seen = set()
    normalized = []
    for hashtag in hashtags or []:
        cleaned = hashtag.strip()
        if not cleaned:
            continue
        if not cleaned.startswith("#"):
            cleaned = f"#{cleaned}"
        if cleaned not in seen:
            seen.add(cleaned)
            normalized.append(cleaned)
    return normalized


def compose_description(description="", hashtags=None):
    parts = [description.rstrip()] if description else []
    for hashtag in normalize_hashtags(hashtags):
        if description and hashtag in description:
            continue
        parts.append(hashtag)
    return "\n".join(part for part in parts if part)


def read_metadata_fields(metadata_file):
    fields = {}
    with open(metadata_file, "r", encoding="utf-8") as metadata:
        for line in metadata:
            text = line.strip()
            if not text.startswith("-") or ":" not in text:
                continue
            key, value = text[1:].split(":", 1)
            fields[key.strip().lower()] = value.strip()
    return fields


def parse_twitch_crop_records(markdown_data):
    records = []
    current_heading = None
    current_lines = []

    def flush_record():
        if current_heading is None:
            return

        fields = {}
        for line in current_lines:
            match = re.match(r"\s*-\s*([^:]+):\s*(.*)\s*$", line)
            if match:
                fields[match.group(1).strip().lower()] = match.group(2).strip()

        records.append(
            {
                "number": current_heading.lstrip("#").strip(),
                "emoji": fields.get("emoji", ""),
                "title": fields.get("title", ""),
                "second-title": fields.get("second-title", ""),
                "start": fields.get("start", ""),
                "end": fields.get("end", ""),
            }
        )

    for raw_line in markdown_data.replace("\ufeff", "").splitlines():
        if re.match(r"^##\s+\S+", raw_line):
            flush_record()
            current_heading = raw_line.strip()
            current_lines = []
        elif current_heading is not None:
            current_lines.append(raw_line.rstrip())

    flush_record()
    return records


def read_twitch_crop_records(root_dir):
    records_path = os.path.join(root_dir, "twitch-crop-records.md")
    if not os.path.isfile(records_path):
        raise FileNotFoundError(f"twitch-crop-records.md not found: {records_path}")

    with open(records_path, "r", encoding="utf-8-sig") as records_file:
        return parse_twitch_crop_records(records_file.read())


def normalize_time_for_custom_folder(time_text):
    return "".join(part.zfill(2) for part in time_text.strip().split(":"))


def build_title_from_fields(fields):
    title_parts = [
        fields.get("emoji", ""),
        fields.get("title", ""),
        fields.get("second-title", ""),
    ]
    return " ".join(part for part in title_parts if part)


def build_title_from_metadata(metadata_file):
    fields = read_metadata_fields(metadata_file)
    return build_title_from_fields(fields)


def get_clip_folder_candidates(root_dir, record):
    candidates = []
    title = record.get("title", "")
    if title:
        candidates.append(clean_filename(title))

    start = record.get("start", "")
    end = record.get("end", "")
    if start and end:
        start_part = normalize_time_for_custom_folder(start)
        end_part = normalize_time_for_custom_folder(end)
        candidates.append(f"Custom_{start_part}_{end_part}")

    return [os.path.join(root_dir, candidate) for candidate in candidates]


def find_clip_folder(root_dir, record):
    for clip_folder in get_clip_folder_candidates(root_dir, record):
        if os.path.isdir(clip_folder):
            return clip_folder

    return None


def find_clip_folder_with_video(root_dir, record, video_filename):
    fallback_folder = None
    for clip_folder in get_clip_folder_candidates(root_dir, record):
        if not os.path.isdir(clip_folder):
            continue
        if fallback_folder is None:
            fallback_folder = clip_folder
        if os.path.isfile(os.path.join(clip_folder, video_filename)):
            return clip_folder

    return fallback_folder


def build_batch_uploads(root_dir, video_filename=DEFAULT_VIDEO_FILENAME):
    root_dir = os.path.abspath(root_dir)
    uploads = []
    skipped = []

    for record in read_twitch_crop_records(root_dir):
        title = build_title_from_fields(record)
        if not title:
            skipped.append((record, "missing title"))
            continue

        clip_folder = find_clip_folder_with_video(root_dir, record, video_filename)
        if not clip_folder:
            skipped.append((record, "clip folder not found"))
            continue

        video_file = os.path.join(clip_folder, video_filename)
        if not os.path.isfile(video_file):
            skipped.append((record, f"video not found: {video_filename}"))
            continue

        thumbnail_file = os.path.join(clip_folder, DEFAULT_THUMBNAIL_FILENAME)
        if not os.path.isfile(thumbnail_file):
            thumbnail_file = None

        uploads.append(
            {
                "record": record,
                "clip_folder": clip_folder,
                "video_file": video_file,
                "thumbnail_file": thumbnail_file,
                "title": title,
            }
        )

    return uploads, skipped


def build_video_body(
    title,
    description="",
    privacy="private",
    publish_time=None,
    tags=None,
    category_id="22",
    made_for_kids=False,
):
    status = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": made_for_kids,
    }
    if publish_time is not None:
        status["privacyStatus"] = "private"
        status["publishAt"] = to_rfc3339(publish_time)

    snippet = {"title": title, "description": description, "categoryId": category_id}
    if tags:
        snippet["tags"] = tags

    return {"snippet": snippet, "status": status}


def add_video_to_playlist(service, video_id, playlist_id, position=None):
    snippet = {
        "playlistId": playlist_id,
        "resourceId": {
            "kind": "youtube#video",
            "videoId": video_id,
        },
    }
    if position is not None:
        snippet["position"] = position

    body = {"snippet": snippet}
    print(f"Adding video to playlist: {playlist_id}")
    service.playlistItems().insert(part="snippet", body=body).execute()


def upload_video(
    video_file,
    title,
    thumbnail_file=None,
    publish_time=None,
    description="",
    hashtags=None,
    privacy="private",
    category_id="22",
    tags=None,
    made_for_kids=False,
    playlist_id=None,
    playlist_position=None,
    client_secrets_file=DEFAULT_CLIENT_SECRETS,
    token_file=DEFAULT_TOKEN_FILE,
    use_console=False,
):
    if build is None or MediaFileUpload is None:
        raise RuntimeError(
            "google-api-python-client is required. Install dependencies with `uv sync`."
        )
    if not os.path.isfile(video_file):
        raise FileNotFoundError(f"Video file not found: {video_file}")
    if thumbnail_file and not os.path.isfile(thumbnail_file):
        raise FileNotFoundError(f"Thumbnail file not found: {thumbnail_file}")

    creds = load_credentials(client_secrets_file, token_file, use_console=use_console)
    service = build("youtube", "v3", credentials=creds)

    body = build_video_body(
        title=title,
        description=compose_description(description, hashtags),
        privacy=privacy,
        publish_time=publish_time,
        tags=tags,
        category_id=category_id,
        made_for_kids=made_for_kids,
    )

    media = MediaFileUpload(video_file, chunksize=1024 * 1024 * 8, resumable=True)
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    print(f"Uploading video: {video_file}")
    while response is None:
        status, response = request.next_chunk()
        if status:
            progress = int(status.progress() * 100)
            print(f"Upload progress: {progress}%")

    video_id = response["id"]
    print(f"Uploaded video id: {video_id}")

    if thumbnail_file:
        print(f"Uploading thumbnail: {thumbnail_file}")
        thumbnail_media = MediaFileUpload(thumbnail_file)
        service.thumbnails().set(videoId=video_id, media_body=thumbnail_media).execute()

    if playlist_id:
        add_video_to_playlist(
            service,
            video_id,
            playlist_id,
            position=playlist_position,
        )

    return video_id


def main():
    parser = argparse.ArgumentParser(description="Upload a video to YouTube")
    parser.add_argument(
        "target",
        help=(
            "Path to a video file, or a root directory containing "
            "twitch-crop-records.md and clip folders"
        ),
    )
    parser.add_argument("--title", help="YouTube video title")
    parser.add_argument(
        "--metadata",
        help="Read Title and Second-title from metadata.md and use them as the upload title",
    )
    parser.add_argument("--thumbnail", help="Path to thumbnail image")
    parser.add_argument(
        "--publish_time",
        help="Scheduled publish time in ISO-8601 format, e.g. 2026-06-20T15:00:00Z",
    )
    parser.add_argument("--description", default=DEFAULT_DESCRIPTION, help="Video description")
    parser.add_argument(
        "--description_file",
        help="Read the description from a UTF-8 text file",
    )
    parser.add_argument(
        "--hashtag",
        action="append",
        dest="hashtags",
        help="Visible hashtag to append to the description (repeatable)",
    )
    parser.add_argument(
        "--privacy",
        choices=("private", "unlisted", "public"),
        default="private",
        help="Privacy status when not scheduling (default: private)",
    )
    parser.add_argument("--category_id", default="22", help="YouTube category id")
    parser.add_argument(
        "--tag",
        action="append",
        dest="tags",
        help="Video tag (repeatable)",
    )
    parser.add_argument(
        "--made_for_kids",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Self-declare whether this video is made for kids (default: False)",
    )
    parser.add_argument(
        "--playlist_id",
        default=DEFAULT_PLAYLIST_ID,
        help="Playlist ID to add the uploaded video to after upload",
    )
    parser.add_argument(
        "--playlist_position",
        type=int,
        help="Optional zero-based position when adding to the playlist",
    )
    parser.add_argument(
        "--client_secrets",
        default=DEFAULT_CLIENT_SECRETS,
        help="OAuth client secrets JSON file",
    )
    parser.add_argument(
        "--token_file",
        default=DEFAULT_TOKEN_FILE,
        help="File used to cache OAuth tokens",
    )
    parser.add_argument(
        "--auth_console",
        action="store_true",
        help="Use console-based OAuth flow instead of local server",
    )
    parser.add_argument(
        "--video_filename",
        default=DEFAULT_VIDEO_FILENAME,
        help="Clip video filename used in root-dir batch mode",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Print the videos that would be uploaded without uploading",
    )
    args = parser.parse_args()

    description = args.description
    if args.description_file:
        with open(args.description_file, "r", encoding="utf-8") as description_file:
            description = description_file.read().rstrip("\n")

    hashtags = args.hashtags if args.hashtags is not None else DEFAULT_HASHTAGS
    tags = args.tags if args.tags is not None else DEFAULT_TAGS

    publish_time = parse_publish_time(args.publish_time)

    if os.path.isdir(args.target):
        uploads, skipped = build_batch_uploads(
            args.target,
            video_filename=args.video_filename,
        )

        for record, reason in skipped:
            print(f"Skipping record {record.get('number')}: {reason}")

        if not uploads:
            parser.error("No uploadable clips found in root directory")

        for index, item in enumerate(uploads, start=1):
            print(
                f"[{index}/{len(uploads)}] "
                f"{item['title']} -> {item['video_file']}"
            )
            if args.dry_run:
                continue

            upload_video(
                item["video_file"],
                title=item["title"],
                thumbnail_file=item["thumbnail_file"],
                publish_time=publish_time,
                description=description,
                hashtags=hashtags,
                privacy=args.privacy,
                category_id=args.category_id,
                tags=tags,
                made_for_kids=args.made_for_kids,
                playlist_id=args.playlist_id,
                playlist_position=args.playlist_position,
                client_secrets_file=args.client_secrets,
                token_file=args.token_file,
                use_console=args.auth_console,
            )
        return

    if not os.path.isfile(args.target):
        parser.error(f"target is not a file or directory: {args.target}")

    title = args.title
    if args.metadata:
        title = build_title_from_metadata(args.metadata)
    if not title:
        parser.error("--title is required unless --metadata provides a Title")

    upload_video(
        args.target,
        title=title,
        thumbnail_file=args.thumbnail,
        publish_time=publish_time,
        description=description,
        hashtags=hashtags,
        privacy=args.privacy,
        category_id=args.category_id,
        tags=tags,
        made_for_kids=args.made_for_kids,
        playlist_id=args.playlist_id,
        playlist_position=args.playlist_position,
        client_secrets_file=args.client_secrets,
        token_file=args.token_file,
        use_console=args.auth_console,
    )


if __name__ == "__main__":
    main()
