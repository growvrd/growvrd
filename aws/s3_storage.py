"""
AWS S3 Storage Manager for GrowVRD

This module provides file storage capabilities using AWS S3 for plant images,
user uploads, and other static assets with proper security and optimization.
"""
import os
import uuid
import mimetypes
import logging
from typing import Dict, List, Any, Optional, Union, BinaryIO
from datetime import datetime, timedelta
from urllib.parse import urlparse
from PIL import Image, ImageOps
import io

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from werkzeug.utils import secure_filename

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('s3_storage')


class S3StorageError(Exception):
    """Exception raised for S3 storage errors"""
    pass


class S3StorageManager:
    """
    S3 storage manager with image processing, security, and optimization
    """

    def __init__(self):
        """Initialize S3 storage manager"""
        self.region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        self.bucket_name = os.getenv('S3_BUCKET_NAME', 'growvrd-storage')

        # Initialize S3 client
        try:
            self.s3_client = boto3.client(
                's3',
                region_name=self.region,
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
            )
            logger.info("S3 client initialized successfully")
        except Exception as e:
            raise S3StorageError(f"Failed to initialize S3 client: {str(e)}")

        # Storage configuration
        self.max_file_size = 10 * 1024 * 1024  # 10MB
        self.allowed_image_types = {'jpg', 'jpeg', 'png', 'webp'}
        self.allowed_document_types = {'pdf', 'txt', 'csv', 'tsv'}

        # Image processing settings
        self.image_quality = 85
        self.thumbnail_sizes = {
            'small': (150, 150),
            'medium': (300, 300),
            'large': (800, 600)
        }

        # Storage paths
        self.paths = {
            'plant_images': 'plants/images/',
            'user_uploads': 'users/uploads/',
            'product_images': 'products/images/',
            'kit_images': 'kits/images/',
            'thumbnails': 'thumbnails/',
            'temp': 'temp/'
        }

    def _validate_file(self, file_data: Union[bytes, BinaryIO], filename: str, file_type: str = 'image') -> bool:
        """
        Validate file type, size, and content

        Args:
            file_data: File data (bytes or file object)
            filename: Original filename
            file_type: Expected file type ('image' or 'document')

        Returns:
            True if file is valid

        Raises:
            S3StorageError: If file validation fails
        """
        # Get file size
        if hasattr(file_data, 'seek'):
            # File object
            file_data.seek(0, 2)  # Seek to end
            file_size = file_data.tell()
            file_data.seek(0)  # Reset to beginning
        else:
            # Bytes
            file_size = len(file_data)

        # Check file size
        if file_size > self.max_file_size:
            raise S3StorageError(f"File too large: {file_size} bytes (max: {self.max_file_size})")

        if file_size == 0:
            raise S3StorageError("File is empty")

        # Get file extension
        file_ext = secure_filename(filename).lower().split('.')[-1] if '.' in filename else ''

        # Validate file type
        if file_type == 'image':
            if file_ext not in self.allowed_image_types:
                raise S3StorageError(f"Invalid image type: {file_ext}. Allowed: {self.allowed_image_types}")

            # Validate image content
            try:
                if hasattr(file_data, 'read'):
                    image_data = file_data.read()
                    file_data.seek(0)
                else:
                    image_data = file_data

                with Image.open(io.BytesIO(image_data)) as img:
                    img.verify()  # Verify it's a valid image

            except Exception as e:
                raise S3StorageError(f"Invalid image file: {str(e)}")

        elif file_type == 'document':
            if file_ext not in self.allowed_document_types:
                raise S3StorageError(f"Invalid document type: {file_ext}. Allowed: {self.allowed_document_types}")

        return True

    def _generate_key(self, path: str, filename: str, user_id: str = None) -> str:
        """
        Generate secure S3 key for file storage

        Args:
            path: Storage path category
            filename: Original filename
            user_id: Optional user ID for user-specific files

        Returns:
            Secure S3 key
        """
        # Secure the filename
        safe_filename = secure_filename(filename)

        # Generate unique identifier
        unique_id = uuid.uuid4().hex[:8]

        # Get file extension
        file_ext = safe_filename.split('.')[-1] if '.' in safe_filename else ''

        # Generate timestamp
        timestamp = datetime.now().strftime('%Y%m%d')

        # Build key
        if user_id:
            key = f"{path}{user_id}/{timestamp}/{unique_id}.{file_ext}"
        else:
            key = f"{path}{timestamp}/{unique_id}.{file_ext}"

        return key

    def _process_image(self, image_data: bytes, max_size: tuple = None, quality: int = None) -> bytes:
        """
        Process and optimize image

        Args:
            image_data: Raw image data
            max_size: Maximum dimensions (width, height)
            quality: JPEG quality (1-100)

        Returns:
            Processed image data
        """
        try:
            with Image.open(io.BytesIO(image_data)) as img:
                # Convert to RGB if necessary
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')

                # Auto-orient based on EXIF data
                img = ImageOps.exif_transpose(img)

                # Resize if max_size specified
                if max_size:
                    img.thumbnail(max_size, Image.Resampling.LANCZOS)

                # Save processed image
                output = io.BytesIO()
                img_format = 'JPEG'
                save_quality = quality or self.image_quality

                img.save(output, format=img_format, quality=save_quality, optimize=True)

                return output.getvalue()

        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            raise S3StorageError(f"Image processing failed: {str(e)}")

    def upload_plant_image(self, image_data: Union[bytes, BinaryIO], filename: str,
                           plant_id: str = None, create_thumbnails: bool = True) -> Dict[str, Any]:
        """
        Upload plant image with automatic processing and thumbnail generation

        Args:
            image_data: Image file data
            filename: Original filename
            plant_id: Optional plant ID for organization
            create_thumbnails: Whether to create thumbnail versions

        Returns:
            Upload result with URLs
        """
        try:
            # Validate image
            self._validate_file(image_data, filename, 'image')

            # Convert to bytes if file object
            if hasattr(image_data, 'read'):
                raw_data = image_data.read()
            else:
                raw_data = image_data

            # Generate key for main image
            main_key = self._generate_key(self.paths['plant_images'], filename)

            # Process main image
            processed_data = self._process_image(raw_data, max_size=(1200, 1200))

            # Upload main image
            self._upload_to_s3(processed_data, main_key, 'image/jpeg')

            # Generate main image URL
            main_url = self._generate_url(main_key)

            result = {
                'success': True,
                'main_image': {
                    'key': main_key,
                    'url': main_url,
                    'size': len(processed_data)
                },
                'thumbnails': {}
            }

            # Create thumbnails if requested
            if create_thumbnails:
                for size_name, dimensions in self.thumbnail_sizes.items():
                    try:
                        # Process thumbnail
                        thumb_data = self._process_image(raw_data, max_size=dimensions, quality=80)

                        # Generate thumbnail key
                        thumb_key = self._generate_key(
                            f"{self.paths['thumbnails']}{size_name}/",
                            filename
                        )

                        # Upload thumbnail
                        self._upload_to_s3(thumb_data, thumb_key, 'image/jpeg')

                        # Add to result
                        result['thumbnails'][size_name] = {
                            'key': thumb_key,
                            'url': self._generate_url(thumb_key),
                            'size': len(thumb_data),
                            'dimensions': dimensions
                        }

                    except Exception as e:
                        logger.error(f"Failed to create {size_name} thumbnail: {str(e)}")

            logger.info(f"Successfully uploaded plant image: {main_key}")
            return result

        except Exception as e:
            logger.error(f"Plant image upload failed: {str(e)}")
            if isinstance(e, S3StorageError):
                raise
            else:
                raise S3StorageError(f"Upload failed: {str(e)}")

    def upload_user_file(self, file_data: Union[bytes, BinaryIO], filename: str,
                         user_id: str, file_type: str = 'image') -> Dict[str, Any]:
        """
        Upload user file with proper security and organization

        Args:
            file_data: File data
            filename: Original filename
            user_id: User ID for file organization
            file_type: File type ('image' or 'document')

        Returns:
            Upload result with URL
        """
        try:
            # Validate file
            self._validate_file(file_data, filename, file_type)

            # Convert to bytes if file object
            if hasattr(file_data, 'read'):
                raw_data = file_data.read()
            else:
                raw_data = file_data

            # Generate key
            file_key = self._generate_key(self.paths['user_uploads'], filename, user_id)

            # Process image if it's an image file
            if file_type == 'image':
                processed_data = self._process_image(raw_data, max_size=(800, 600))
                content_type = 'image/jpeg'
            else:
                processed_data = raw_data
                content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

            # Upload file
            self._upload_to_s3(processed_data, file_key, content_type)

            result = {
                'success': True,
                'key': file_key,
                'url': self._generate_url(file_key),
                'size': len(processed_data),
                'type': file_type
            }

            logger.info(f"Successfully uploaded user file: {file_key}")
            return result

        except Exception as e:
            logger.error(f"User file upload failed: {str(e)}")
            if isinstance(e, S3StorageError):
                raise
            else:
                raise S3StorageError(f"Upload failed: {str(e)}")

    def _upload_to_s3(self, data: bytes, key: str, content_type: str) -> None:
        """
        Upload data to S3 with proper metadata and permissions

        Args:
            data: File data to upload
            key: S3 key
            content_type: MIME type
        """
        try:
            # Prepare metadata
            metadata = {
                'uploaded_at': datetime.now().isoformat(),
                'service': 'growvrd'
            }

            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type,
                Metadata=metadata,
                ServerSideEncryption='AES256'
            )

            logger.debug(f"Uploaded to S3: {key}")

        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"S3 upload failed: {error_code}")
            raise S3StorageError(f"S3 upload failed: {error_code}")
        except Exception as e:
            logger.error(f"Upload error: {str(e)}")
            raise S3StorageError(f"Upload error: {str(e)}")

    def _generate_url(self, key: str, expires_in: int = 3600) -> str:
        """
        Generate signed URL for S3 object

        Args:
            key: S3 key
            expires_in: URL expiration time in seconds

        Returns:
            Signed URL
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': key},
                ExpiresIn=expires_in
            )
            return url

        except Exception as e:
            logger.error(f"Error generating URL for {key}: {str(e)}")
            raise S3StorageError(f"URL generation failed: {str(e)}")

    def get_file(self, key: str) -> Dict[str, Any]:
        """
        Get file information and download URL

        Args:
            key: S3 key

        Returns:
            File information with download URL
        """
        try:
            # Get object metadata
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=key)

            return {
                'success': True,
                'key': key,
                'size': response['ContentLength'],
                'last_modified': response['LastModified'].isoformat(),
                'content_type': response['ContentType'],
                'download_url': self._generate_url(key),
                'metadata': response.get('Metadata', {})
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                return {'success': False, 'error': 'file_not_found', 'message': 'File not found'}
            else:
                logger.error(f"Error getting file {key}: {error_code}")
                return {'success': False, 'error': 'access_error', 'message': 'Failed to access file'}
        except Exception as e:
            logger.error(f"Error getting file {key}: {str(e)}")
            return {'success': False, 'error': 'system_error', 'message': 'System error'}

    def delete_file(self, key: str) -> Dict[str, Any]:
        """
        Delete file from S3

        Args:
            key: S3 key

        Returns:
            Deletion result
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)

            logger.info(f"Deleted file: {key}")
            return {'success': True, 'message': 'File deleted successfully'}

        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Error deleting file {key}: {error_code}")
            return {'success': False, 'error': 'deletion_failed', 'message': 'Failed to delete file'}
        except Exception as e:
            logger.error(f"Error deleting file {key}: {str(e)}")
            return {'success': False, 'error': 'system_error', 'message': 'System error'}

    def list_user_files(self, user_id: str, file_type: str = None) -> Dict[str, Any]:
        """
        List files for a specific user

        Args:
            user_id: User ID
            file_type: Optional file type filter

        Returns:
            List of user files
        """
        try:
            # Build prefix
            prefix = f"{self.paths['user_uploads']}{user_id}/"

            # List objects
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )

            files = []
            for obj in response.get('Contents', []):
                key = obj['Key']

                # Skip if file type filter specified and doesn't match
                if file_type:
                    file_ext = key.split('.')[-1].lower()
                    if file_type == 'image' and file_ext not in self.allowed_image_types:
                        continue
                    elif file_type == 'document' and file_ext not in self.allowed_document_types:
                        continue

                files.append({
                    'key': key,
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'].isoformat(),
                    'download_url': self._generate_url(key)
                })

            return {
                'success': True,
                'files': files,
                'count': len(files)
            }

        except Exception as e:
            logger.error(f"Error listing user files: {str(e)}")
            return {'success': False, 'error': 'system_error', 'message': 'Failed to list files'}

    def cleanup_temp_files(self, max_age_hours: int = 24) -> Dict[str, Any]:
        """
        Clean up temporary files older than specified age

        Args:
            max_age_hours: Maximum age of temp files in hours

        Returns:
            Cleanup result
        """
        try:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

            # List temp files
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=self.paths['temp']
            )

            deleted_count = 0
            for obj in response.get('Contents', []):
                if obj['LastModified'] < cutoff_time.replace(tzinfo=obj['LastModified'].tzinfo):
                    try:
                        self.s3_client.delete_object(Bucket=self.bucket_name, Key=obj['Key'])
                        deleted_count += 1
                    except Exception as e:
                        logger.error(f"Failed to delete temp file {obj['Key']}: {str(e)}")

            logger.info(f"Cleaned up {deleted_count} temporary files")
            return {
                'success': True,
                'deleted_count': deleted_count,
                'message': f'Cleaned up {deleted_count} temporary files'
            }

        except Exception as e:
            logger.error(f"Error cleaning up temp files: {str(e)}")
            return {'success': False, 'error': 'cleanup_failed', 'message': 'Cleanup failed'}

    def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics for the bucket

        Returns:
            Storage statistics
        """
        try:
            stats = {
                'total_objects': 0,
                'total_size': 0,
                'categories': {}
            }

            # Get all objects
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket_name)

            for page in pages:
                for obj in page.get('Contents', []):
                    stats['total_objects'] += 1
                    stats['total_size'] += obj['Size']

                    # Categorize by path
                    key = obj['Key']
                    category = 'other'
                    for path_name, path_prefix in self.paths.items():
                        if key.startswith(path_prefix):
                            category = path_name
                            break

                    if category not in stats['categories']:
                        stats['categories'][category] = {'count': 0, 'size': 0}

                    stats['categories'][category]['count'] += 1
                    stats['categories'][category]['size'] += obj['Size']

            # Convert bytes to human readable
            stats['total_size_mb'] = round(stats['total_size'] / (1024 * 1024), 2)

            for category in stats['categories']:
                size_bytes = stats['categories'][category]['size']
                stats['categories'][category]['size_mb'] = round(size_bytes / (1024 * 1024), 2)

            return {
                'success': True,
                'stats': stats,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error getting storage stats: {str(e)}")
            return {'success': False, 'error': 'stats_failed', 'message': 'Failed to get stats'}

    def health_check(self) -> Dict[str, Any]:
        """
        Check S3 connection and bucket access

        Returns:
            Health check result
        """
        try:
            # Test bucket access
            self.s3_client.head_bucket(Bucket=self.bucket_name)

            # Test upload/download with a small test file
            test_key = f"{self.paths['temp']}health_check_{uuid.uuid4().hex[:8]}.txt"
            test_data = b"health check test"

            # Upload test file
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=test_key,
                Body=test_data,
                ContentType='text/plain'
            )

            # Download test file
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=test_key)
            downloaded_data = response['Body'].read()

            # Clean up test file
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=test_key)

            # Verify data integrity
            if downloaded_data == test_data:
                return {
                    'success': True,
                    'bucket': self.bucket_name,
                    'region': self.region,
                    'status': 'healthy',
                    'timestamp': datetime.now().isoformat()
                }
            else:
                return {
                    'success': False,
                    'status': 'data_integrity_error',
                    'message': 'Data integrity check failed'
                }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"S3 health check failed: {error_code}")

            if error_code == 'NoSuchBucket':
                return {'success': False, 'status': 'bucket_not_found',
                        'message': f'Bucket {self.bucket_name} not found'}
            elif error_code == 'AccessDenied':
                return {'success': False, 'status': 'access_denied', 'message': 'Access denied to bucket'}
            else:
                return {'success': False, 'status': 'error', 'message': f'S3 error: {error_code}'}

        except Exception as e:
            logger.error(f"S3 health check error: {str(e)}")
            return {'success': False, 'status': 'error', 'message': str(e)}


# Global storage manager instance
_s3_manager = None


def get_s3_manager() -> S3StorageManager:
    """Get global S3 storage manager instance"""
    global _s3_manager
    if _s3_manager is None:
        _s3_manager = S3StorageManager()
    return _s3_manager


# Convenience functions
def upload_plant_image(image_data: Union[bytes, BinaryIO], filename: str,
                       plant_id: str = None) -> Dict[str, Any]:
    """Upload plant image (convenience function)"""
    return get_s3_manager().upload_plant_image(image_data, filename, plant_id)


def upload_user_file(file_data: Union[bytes, BinaryIO], filename: str,
                     user_id: str, file_type: str = 'image') -> Dict[str, Any]:
    """Upload user file (convenience function)"""
    return get_s3_manager().upload_user_file(file_data, filename, user_id, file_type)


def get_file_url(key: str, expires_in: int = 3600) -> str:
    """Get file download URL (convenience function)"""
    return get_s3_manager()._generate_url(key, expires_in)


def delete_file(key: str) -> Dict[str, Any]:
    """Delete file (convenience function)"""
    return get_s3_manager().delete_file(key)


def s3_health_check() -> Dict[str, Any]:
    """S3 health check (convenience function)"""
    try:
        return get_s3_manager().health_check()
    except Exception as e:
        return {'success': False, 'status': 'error', 'message': str(e)}


if __name__ == "__main__":
    # Test the storage manager
    try:
        health = s3_health_check()
        print("S3 Health Check:", health)

        if health['success']:
            manager = get_s3_manager()
            stats = manager.get_storage_stats()
            print("Storage Stats:", stats)
    except Exception as e:
        print(f"Error testing S3 storage manager: {e}")