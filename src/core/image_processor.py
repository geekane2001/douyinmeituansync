"""
图片处理模块 - 处理图片裁剪和上传到R2
"""
import boto3
from botocore.client import Config
from io import BytesIO
import datetime
from PIL import Image

from src.config import (
    CLOUDFLARE_R2_ACCESS_KEY_ID,
    CLOUDFLARE_R2_SECRET_ACCESS_KEY,
    R2_ENDPOINT_URL,
    R2_BUCKET_NAME,
    R2_PUBLIC_URL_PREFIX
)


def center_crop_image(img, aspect_ratio):
    """居中裁剪图片到指定宽高比"""
    width, height = img.size
    target_width, target_height = width, width / aspect_ratio
    
    if target_height > height:
        target_height = height
        target_width = height * aspect_ratio
    
    left = (width - target_width) / 2
    top = (height - target_height) / 2
    
    return img.crop((left, top, left + target_width, top + target_height))


def upload_to_r2(img_obj, poi_id, aspect_ratio_str, log_func):
    """上传图片到Cloudflare R2存储"""
    log_func(f"--- 正在上传 {aspect_ratio_str} 比例的图片 ---")
    
    try:
        s3_client = boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT_URL,
            aws_access_key_id=CLOUDFLARE_R2_ACCESS_KEY_ID,
            aws_secret_access_key=CLOUDFLARE_R2_SECRET_ACCESS_KEY,
            config=Config(signature_version='s3v4')
        )
        
        in_mem_file = BytesIO()
        if img_obj.mode == 'RGBA':
            img_obj = img_obj.convert('RGB')
        img_obj.save(in_mem_file, format='JPEG', quality=90)
        in_mem_file.seek(0)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{poi_id}_{timestamp}_{aspect_ratio_str.replace(':', '_')}.jpg"
        
        s3_client.upload_fileobj(
            in_mem_file,
            R2_BUCKET_NAME,
            filename,
            ExtraArgs={'ContentType': 'image/jpeg'}
        )
        
        image_url = f"{R2_PUBLIC_URL_PREFIX}/{filename}"
        log_func(f"[Success] 图片上传成功: {image_url}")
        return image_url
    except Exception as e:
        log_func(f"[Error] 图片上传到R2失败: {e}")
        return None
