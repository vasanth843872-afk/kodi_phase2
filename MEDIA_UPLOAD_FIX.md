# Media Upload Fix Summary

## Issue Description
The post creation with media was failing due to:
1. **Thumbnail filename too long**: Original filenames were being used directly for thumbnails
2. **Database field length limit**: Thumbnail field didn't have sufficient max_length

## Fixes Applied

### 1. Thumbnail Generation Fix (`apps/posts/services.py`)
```python
# Before (causing long filenames)
thumb_filename = f"thumb_{media.original_filename}"

# After (short UUID-based filenames)
import uuid
import os
file_ext = os.path.splitext(media.original_filename)[1]
if not file_ext:
    file_ext = '.jpg'
thumb_filename = f"thumb_{uuid.uuid4().hex[:12]}{file_ext}"
```

### 2. Database Field Fix (`apps/posts/models.py`)
```python
# Before (using default max_length)
thumbnail = models.ImageField(
    upload_to='post_thumbnails/%Y/%m/%d/',
    null=True,
    blank=True
)

# After (explicit max_length)
thumbnail = models.ImageField(
    upload_to='post_thumbnails/%Y/%m/%d/',
    null=True,
    blank=True,
    max_length=500
)
```

### 3. Applied Migrations
```bash
python manage.py makemigrations posts
python manage.py migrate
```

## ✅ Correct Payload Formats

### **Option 1: Create Post with Media (Single Request)**
```
POST /api/posts/create/
Content-Type: multipart/form-data
Authorization: Bearer your_token

Form Data:
- content: "jjhw"
- visibility: "connections"
- media: [your binary file]
- media_captions: "hhhh"
```

### **Option 2: Create Post First, Then Add Media (Recommended)**
**Step 1: Create post**
```json
POST /api/posts/create/
Content-Type: application/json
Authorization: Bearer your_token

{
    "content": "jjhw",
    "visibility": "connections"
}
```

**Step 2: Add media**
```
POST /api/posts/{post_id}/media/upload/
Content-Type: multipart/form-data
Authorization: Bearer your_token

Form Data:
- media: [your binary file]
- media_captions: "hhhh"
```

### **Option 3: Multiple Media Files**
```
POST /api/posts/create/
Content-Type: multipart/form-data
Authorization: Bearer your_token

Form Data:
- content: "Multiple media test"
- visibility: "connections"
- media: [file1.jpg]
- media: [file2.jpg]
- media_captions: "First image caption"
- media_captions: "Second image caption"
```

## 🧪 Testing Commands

### **cURL Example**
```bash
curl -X POST http://localhost:8000/api/posts/create/ \
  -H "Authorization: Bearer your_token" \
  -F "content=jjhw" \
  -F "visibility=connections" \
  -F "media=@your_image_file.jpg" \
  -F "media_captions=hhhh"
```

### **Postman/Insomnia Setup**
- Method: POST
- URL: `http://localhost:8000/api/posts/create/`
- Headers:
  - Authorization: `Bearer your_token`
  - Content-Type: `multipart/form-data` (auto-set by tool)
- Body:
  - Form-data
  - Add fields: content, visibility, media, media_captions

## 📋 Supported File Types

### **Images** (thumbnails generated)
- jpg, jpeg, png, gif, webp
- Max size: 10MB (configurable)

### **Videos**
- mp4, avi, mov, wmv
- Max size: 50MB (configurable)

### **Documents** (no thumbnails)
- pdf, doc, docx, txt
- Max size: 10MB (configurable)

### **Audio**
- mp3, wav, flac
- Max size: 10MB (configurable)

## 🔧 Configuration Settings

Add to `settings.py` if needed:
```python
# Post media settings
POST_MEDIA_MAX_SIZE = 10 * 1024 * 1024  # 10MB
POST_MEDIA_ALLOWED_TYPES = ['image', 'video', 'document', 'audio']
```

## ✅ Verification

The media upload should now work correctly with:
- ✅ Short thumbnail filenames (UUID-based)
- ✅ Proper database field lengths
- ✅ Support for all file types
- ✅ Automatic thumbnail generation for images
- ✅ Error handling for unsupported files

## 🚀 Ready for Testing

Your payload format was correct! The issue was with the backend thumbnail generation. Now it should work perfectly.
