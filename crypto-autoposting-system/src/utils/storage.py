"""
Storage service for files and media
"""
import logging
import asyncio
import io
import base64
from datetime import datetime
from typing import Optional, BinaryIO
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from ..config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """File storage service using S3-compatible storage"""
    
    def __init__(self):
        self.s3_client = None
        self._initialize_s3()
    
    def _initialize_s3(self):
        """Initialize S3/MinIO client"""
        try:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=settings.s3_endpoint,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                region_name='us-east-1'  # Default region for MinIO
            )
            
            # Test connection and create bucket if needed
            self._ensure_bucket_exists()
            
            logger.info("S3 storage client initialized successfully")
            
        except (NoCredentialsError, Exception) as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            self.s3_client = None
    
    def _ensure_bucket_exists(self):
        """Ensure the storage bucket exists"""
        try:
            self.s3_client.head_bucket(Bucket=settings.s3_bucket)
        except ClientError as e:
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                # Bucket doesn't exist, create it
                try:
                    self.s3_client.create_bucket(Bucket=settings.s3_bucket)
                    logger.info(f"Created bucket: {settings.s3_bucket}")
                except Exception as create_error:
                    logger.error(f"Failed to create bucket: {create_error}")
            else:
                logger.error(f"Error checking bucket: {e}")
    
    async def upload_file(self, file_path: str, object_key: str, content_type: str = None) -> Optional[str]:
        """Upload file to storage"""
        try:
            if not self.s3_client:
                logger.error("S3 client not initialized")
                return None
            
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            
            # Upload file
            self.s3_client.upload_file(
                file_path,
                settings.s3_bucket,
                object_key,
                ExtraArgs=extra_args
            )
            
            # Generate URL
            url = f"{settings.s3_endpoint}/{settings.s3_bucket}/{object_key}"
            
            logger.info(f"Uploaded file to: {url}")
            return url
            
        except Exception as e:
            logger.error(f"Failed to upload file {file_path}: {e}")
            return None
    
    async def upload_from_buffer(self, buffer: BinaryIO, object_key: str, content_type: str = None) -> Optional[str]:
        """Upload from buffer/stream to storage"""
        try:
            if not self.s3_client:
                logger.error("S3 client not initialized")
                return None
            
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            
            # Upload from buffer
            self.s3_client.upload_fileobj(
                buffer,
                settings.s3_bucket,
                object_key,
                ExtraArgs=extra_args
            )
            
            # Generate URL
            url = f"{settings.s3_endpoint}/{settings.s3_bucket}/{object_key}"
            
            logger.info(f"Uploaded buffer to: {url}")
            return url
            
        except Exception as e:
            logger.error(f"Failed to upload buffer: {e}")
            return None
    
    async def upload_image_from_base64(self, base64_data: str, filename: str) -> Optional[str]:
        """Upload image from base64 data"""
        try:
            # Decode base64
            image_data = base64.b64decode(base64_data)
            
            # Create buffer
            buffer = io.BytesIO(image_data)
            
            # Generate object key with timestamp
            timestamp = datetime.utcnow().strftime('%Y/%m/%d')
            object_key = f"images/{timestamp}/{filename}"
            
            # Upload with image content type
            return await self.upload_from_buffer(buffer, object_key, "image/png")
            
        except Exception as e:
            logger.error(f"Failed to upload base64 image: {e}")
            return None
    
    async def upload_image_from_buffer(self, buffer: BinaryIO, filename: str) -> Optional[str]:
        """Upload image from buffer"""
        try:
            # Generate object key with timestamp
            timestamp = datetime.utcnow().strftime('%Y/%m/%d')
            object_key = f"images/{timestamp}/{filename}"
            
            # Determine content type
            content_type = "image/png"
            if filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
                content_type = "image/jpeg"
            elif filename.lower().endswith('.gif'):
                content_type = "image/gif"
            elif filename.lower().endswith('.webp'):
                content_type = "image/webp"
            
            # Upload
            return await self.upload_from_buffer(buffer, object_key, content_type)
            
        except Exception as e:
            logger.error(f"Failed to upload image buffer: {e}")
            return None
    
    async def download_file(self, object_key: str, local_path: str) -> bool:
        """Download file from storage"""
        try:
            if not self.s3_client:
                logger.error("S3 client not initialized")
                return False
            
            self.s3_client.download_file(settings.s3_bucket, object_key, local_path)
            
            logger.info(f"Downloaded {object_key} to {local_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download file {object_key}: {e}")
            return False
    
    async def get_file_buffer(self, object_key: str) -> Optional[io.BytesIO]:
        """Get file as buffer"""
        try:
            if not self.s3_client:
                logger.error("S3 client not initialized")
                return None
            
            buffer = io.BytesIO()
            self.s3_client.download_fileobj(settings.s3_bucket, object_key, buffer)
            buffer.seek(0)
            
            return buffer
            
        except Exception as e:
            logger.error(f"Failed to get file buffer {object_key}: {e}")
            return None
    
    async def delete_file(self, object_key: str) -> bool:
        """Delete file from storage"""
        try:
            if not self.s3_client:
                logger.error("S3 client not initialized")
                return False
            
            self.s3_client.delete_object(Bucket=settings.s3_bucket, Key=object_key)
            
            logger.info(f"Deleted file: {object_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete file {object_key}: {e}")
            return False
    
    async def file_exists(self, object_key: str) -> bool:
        """Check if file exists in storage"""
        try:
            if not self.s3_client:
                return False
            
            self.s3_client.head_object(Bucket=settings.s3_bucket, Key=object_key)
            return True
            
        except ClientError as e:
            if int(e.response['Error']['Code']) == 404:
                return False
            logger.error(f"Error checking file existence {object_key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error checking file existence {object_key}: {e}")
            return False
    
    async def get_file_url(self, object_key: str, expires_in: int = 3600) -> Optional[str]:
        """Generate presigned URL for file access"""
        try:
            if not self.s3_client:
                logger.error("S3 client not initialized")
                return None
            
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': settings.s3_bucket, 'Key': object_key},
                ExpiresIn=expires_in
            )
            
            return url
            
        except Exception as e:
            logger.error(f"Failed to generate presigned URL for {object_key}: {e}")
            return None
    
    async def list_files(self, prefix: str = "", max_keys: int = 100) -> list:
        """List files in storage with optional prefix"""
        try:
            if not self.s3_client:
                logger.error("S3 client not initialized")
                return []
            
            response = self.s3_client.list_objects_v2(
                Bucket=settings.s3_bucket,
                Prefix=prefix,
                MaxKeys=max_keys
            )
            
            files = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    files.append({
                        'key': obj['Key'],
                        'size': obj['Size'],
                        'modified': obj['LastModified'].isoformat(),
                        'url': f"{settings.s3_endpoint}/{settings.s3_bucket}/{obj['Key']}"
                    })
            
            return files
            
        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            return []
    
    async def cleanup_old_files(self, days_old: int = 30):
        """Clean up files older than specified days"""
        try:
            if not self.s3_client:
                logger.error("S3 client not initialized")
                return
            
            from datetime import timedelta
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            
            # List all files
            response = self.s3_client.list_objects_v2(Bucket=settings.s3_bucket)
            
            deleted_count = 0
            if 'Contents' in response:
                for obj in response['Contents']:
                    if obj['LastModified'].replace(tzinfo=None) < cutoff_date:
                        try:
                            await self.delete_file(obj['Key'])
                            deleted_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to delete old file {obj['Key']}: {e}")
            
            logger.info(f"Cleaned up {deleted_count} old files")
            
        except Exception as e:
            logger.error(f"Failed to cleanup old files: {e}")
    
    def get_storage_stats(self) -> dict:
        """Get storage usage statistics"""
        try:
            if not self.s3_client:
                return {"error": "S3 client not initialized"}
            
            response = self.s3_client.list_objects_v2(Bucket=settings.s3_bucket)
            
            stats = {
                "total_files": 0,
                "total_size": 0,
                "file_types": {}
            }
            
            if 'Contents' in response:
                for obj in response['Contents']:
                    stats["total_files"] += 1
                    stats["total_size"] += obj['Size']
                    
                    # Count file types
                    file_ext = obj['Key'].split('.')[-1].lower() if '.' in obj['Key'] else 'unknown'
                    stats["file_types"][file_ext] = stats["file_types"].get(file_ext, 0) + 1
            
            # Convert size to human readable
            stats["total_size_human"] = self._human_readable_size(stats["total_size"])
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get storage stats: {e}")
            return {"error": str(e)}
    
    def _human_readable_size(self, size_bytes: int) -> str:
        """Convert bytes to human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"


# Global storage service instance
storage_service = StorageService()


# Standalone functions
async def upload_file_to_storage(file_path: str, filename: str = None) -> Optional[str]:
    """Upload file to storage"""
    import os
    if not filename:
        filename = os.path.basename(file_path)
    
    timestamp = datetime.utcnow().strftime('%Y/%m/%d')
    object_key = f"uploads/{timestamp}/{filename}"
    
    return await storage_service.upload_file(file_path, object_key)


async def upload_image_data(image_data: bytes, filename: str) -> Optional[str]:
    """Upload image data to storage"""
    buffer = io.BytesIO(image_data)
    return await storage_service.upload_image_from_buffer(buffer, filename)


if __name__ == "__main__":
    # Test storage service
    import asyncio
    
    async def test():
        service = StorageService()
        
        # Test creating a simple file
        test_data = b"Hello, world!"
        buffer = io.BytesIO(test_data)
        
        url = await service.upload_from_buffer(buffer, "test/hello.txt", "text/plain")
        print(f"Uploaded test file: {url}")
        
        # Get storage stats
        stats = service.get_storage_stats()
        print(f"Storage stats: {stats}")
    
    asyncio.run(test())
