import io
import asyncio
import boto3
from botocore.exceptions import ClientError
from core.config import settings

# Initialize the S3 client pointing to DigitalOcean's endpoint
session = boto3.session.Session()
client = session.client(
    "s3",
    region_name=settings.DO_SPACES_REGION,
    endpoint_url=f"https://{settings.DO_SPACES_REGION}.digitaloceanspaces.com",
    aws_access_key_id=settings.DO_SPACES_KEY,
    aws_secret_access_key=settings.DO_SPACES_SECRET,
)


async def _upload_single_page(file_bytes: io.BytesIO, filename: str) -> str | None:
    """Helper function to upload a single file."""
    try:
        object_name = f"batches/{filename}"
        file_bytes.seek(0)

        client.upload_fileobj(
            file_bytes,
            settings.DO_SPACES_BUCKET,
            object_name,
            ExtraArgs={"ACL": "public-read", "ContentType": "application/pdf"},
        )

        return f"https://{settings.DO_SPACES_BUCKET}.{settings.DO_SPACES_REGION}.digitaloceanspaces.com/{object_name}"
    except ClientError as e:
        print(f"S3 Upload Error on {filename}: {e}")
        return None


async def upload_multiple_batch_files(
    files: list[io.BytesIO], base_id: str
) -> list[str]:
    """
    Takes a list of files from The Architect and uploads them concurrently.
    """
    upload_tasks = []

    for index, file_bytes in enumerate(files):
        # Create a unique name for each page: e.g., batch_uuid_page_1.pdf
        page_filename = f"batch_{base_id}_page_{index + 1}.pdf"
        task = _upload_single_page(file_bytes, page_filename)
        upload_tasks.append(task)

    # Execute all uploads at the exact same time
    uploaded_urls = await asyncio.gather(*upload_tasks)

    # Filter out any uploads that failed (returned None)
    return [url for url in uploaded_urls if url is not None]
