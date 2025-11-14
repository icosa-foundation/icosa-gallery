# Batch Thumbnail Generation

The Batch Thumbnail Generator is an admin tool for generating thumbnails for assets that are missing them. It runs entirely in the browser using client-side rendering, which means:

- No server-side rendering infrastructure needed
- Uses the admin's local GPU for 3D rendering
- Admin controls when and how long to run the job
- Can process thumbnails incrementally

## Features

- **Client-Side Rendering**: Uses Three.js and the existing Icosa Viewer to render 3D models directly in the browser
- **Batch Processing**: Process multiple assets automatically with configurable batch sizes
- **Progress Tracking**: Real-time statistics showing completed, failed, and success rate
- **Pause/Resume**: Can pause processing at any time and resume later
- **Skip Assets**: Skip problematic assets that fail to load
- **Live Preview**: See each asset as it's being processed in the 3D viewer
- **Detailed Logging**: Track success and failures with timestamps

## Access

### Via Admin Interface

1. Navigate to the **Assets** admin page: `/admin/icosa/asset/`
2. Click the **"Batch Thumbnail Generator"** button in the top-right toolbar
3. Or use the admin menu to access it directly

### Via Admin Actions

1. Go to the Assets list in admin
2. Filter assets using "thumbnail: Empty" filter to find assets without thumbnails
3. Select specific assets you want to generate thumbnails for
4. Choose **"Generate thumbnails (opens batch generator)"** from the Actions dropdown
5. Click "Go" - this will redirect you to the batch generator

## Setup

### 1. Get a JWT Token

The batch generator requires authentication via JWT. To get your token:

**Option A: Via API Login**
```bash
curl -X POST https://gallery.icosa.io/api/v1/login/jwt \
  -H "Content-Type: application/json" \
  -d '{"username": "your-admin-username", "password": "your-password"}'
```

**Option B: Via Django Shell**
```python
from icosa.models import User

user = User.objects.get(username='your-admin-username')
token = user.generate_jwt_token()
print(token)
```

### 2. Set Token in Browser

Open the batch thumbnail generator page and run this in the browser console:

```javascript
localStorage.setItem('icosa_jwt_token', 'YOUR_TOKEN_HERE')
```

Then refresh the page.

## Usage

### Basic Operation

1. **Configure Settings**:
   - **Batch Size**: Number of assets to process (1-100, default: 50)
   - **Viewer Compatible Only**: Only process assets that can be rendered in the viewer (recommended)

2. **Start Processing**:
   - Click **"Start Generation"** to begin
   - The tool will fetch assets missing thumbnails
   - Each asset will be loaded, rendered, and a screenshot captured
   - The thumbnail is automatically uploaded to the server

3. **Monitor Progress**:
   - Watch the progress bar and statistics
   - View the current asset in the 3D viewer
   - Check the log panel for detailed success/error messages

4. **Control Processing**:
   - **Pause**: Pause processing at any time (can resume later)
   - **Skip Current**: Skip the current asset if it's taking too long or failing
   - Processing automatically stops when all assets are complete

### Tips for Best Results

1. **Run in batches**: Process 50-100 assets at a time rather than thousands
2. **Keep tab active**: Some browsers throttle inactive tabs, affecting rendering
3. **Good internet connection**: Assets need to be downloaded for rendering
4. **Close other tabs**: Free up memory for better 3D rendering performance
5. **Check logs**: Review failed assets to understand issues

### Handling Failures

Common reasons assets might fail:

- **Unsupported format**: Format not supported by the viewer
- **Missing files**: Asset files are missing or inaccessible
- **Corrupted models**: 3D model file is corrupted
- **Large files**: Very large models may timeout or crash
- **Network issues**: Temporary connection problems

Failed assets are logged. You can:
- Manually review and fix the assets
- Re-run the batch generator on failed assets
- Skip assets that can't be fixed

## API Endpoints

The batch generator uses two API endpoints:

### GET `/api/v1/admin/assets/missing-thumbnails`

Fetch assets that need thumbnails.

**Query Parameters**:
- `limit`: Number of assets to return (default: 50, max: 100)
- `offset`: Pagination offset (default: 0)
- `viewer_compatible_only`: Only return viewer-compatible assets (default: true)

**Authentication**: Requires JWT token with staff permissions

**Response**:
```json
{
  "assets": [
    {
      "id": 123,
      "url": "asset-url",
      "name": "Asset Name",
      "owner_displayname": "Owner Name",
      "formats": [
        {
          "format_type": "GLTF2",
          "root_url": "https://...",
          "is_preferred": true
        }
      ]
    }
  ],
  "total_count": 150,
  "has_more": true
}
```

### POST `/api/v1/admin/assets/{asset_id}/thumbnail`

Upload a generated thumbnail for an asset.

**Authentication**: Requires JWT token with staff permissions

**Request Body**:
```json
{
  "thumbnail_base64": "base64-encoded-jpeg-image"
}
```

**Response**:
```json
{
  "success": true,
  "thumbnail_url": "https://...",
  "asset_url": "asset-url"
}
```

## Architecture

### Client-Side Flow

1. **Fetch Assets**: GET request to `/api/v1/admin/assets/missing-thumbnails`
2. **For Each Asset**:
   - Load 3D model using Icosa Viewer
   - Frame the scene (auto-fit camera)
   - Wait for render (500ms)
   - Capture canvas as JPEG (quality 85%)
   - Convert to base64
   - POST to `/api/v1/admin/assets/{id}/thumbnail`
3. **Track Progress**: Update statistics and log results

### Server-Side Processing

1. **Authentication**: Verify JWT token and staff status
2. **Base64 Decode**: Convert base64 string to image bytes
3. **Validation**: Verify image is valid PNG or JPEG using python-magic
4. **Storage**: Save to both `thumbnail` and `preview_image` fields
5. **Upload to B2**: Django storages handles upload to Backblaze B2
6. **Return URL**: Send back the public thumbnail URL

## Troubleshooting

### "JWT token required" Error

- You haven't set the JWT token in localStorage
- Run: `localStorage.setItem('icosa_jwt_token', 'YOUR_TOKEN')`
- Refresh the page

### "Admin access required" Error

- Your user account doesn't have staff permissions
- Contact a superuser to grant you staff status

### Assets Not Loading

- Check browser console for errors
- Verify the asset has a valid format with accessible files
- Check network tab to see if files are downloading
- Some formats may not be supported by the viewer

### Thumbnails Not Saving

- Check the generation log for error messages
- Verify the JWT token is still valid (they expire)
- Check server logs for storage/upload errors

### Performance Issues

- Reduce batch size
- Close other browser tabs
- Ensure good internet connection
- Process lighter assets first (skip large Gaussian splats)

## Future Enhancements

Possible improvements for future versions:

- Automatic retry logic for failed assets
- Configurable thumbnail size and quality
- Custom camera positioning options
- CLI tool for automation
- Queue-based processing with workers
- Support for scheduling batch jobs
- Thumbnail preview before upload confirmation
