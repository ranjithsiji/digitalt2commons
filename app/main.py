from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from urllib.parse import urlparse, urljoin
from werkzeug.utils import secure_filename
from app.uploader import WikimediaUploader
from app.dm_api import DigitaltMuseumClient
import requests
import os
import json
from datetime import datetime

bp = Blueprint('main', __name__)

def is_safe_url(target):
    """Check if the URL is safe for redirection."""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

@bp.route('/')
def index():
    """Home page with URL input form."""
    return render_template('index.html')

@bp.route('/process', methods=['POST'])
def process_url():
    """Process the Digitalt Museum URL and fetch artifact data."""
    dm_url = request.form.get('dm_url', '').strip()
    
    if not dm_url:
        flash('Please enter a Digitalt Museum URL', 'error')
        return redirect(url_for('main.index'))
    
    try:
        artifact_id = extract_artifact_id(dm_url)
        dm_client = DigitaltMuseumClient()
        artifact_data = dm_client.get_artifact(artifact_id)
        
        if not artifact_data:
            flash('Could not retrieve artifact data', 'error')
            return redirect(url_for('main.index'))
        
        # Get media information if available
        if artifact_data.get('media'):
            media_id = artifact_data['media'][0]['mediaId']
            media_data = dm_client.get_media(media_id)
            artifact_data['media_details'] = media_data
            
            # Find best quality image
            image_url = None
            for variant in media_data.get('variants', []):
                if variant['contentType'].startswith('image/'):
                    image_url = variant['url']
                    break
            
            artifact_data['image_url'] = image_url
        
        # Store in session for preview/upload steps
        session['artifact_data'] = artifact_data
        session['image_url'] = artifact_data.get('image_url')
        
        return redirect(url_for('main.preview'))
    
    except Exception as e:
        current_app.logger.error(f"Error processing URL: {str(e)}")
        flash('Error processing the Digitalt Museum URL', 'error')
        return redirect(url_for('main.index'))

@bp.route('/preview')
def preview():
    """Show preview of the artifact before upload."""
    artifact_data = session.get('artifact_data')
    image_url = session.get('image_url')
    
    if not artifact_data or not image_url:
        flash('No artifact data found. Please start over.', 'error')
        return redirect(url_for('main.index'))
    
    # Prepare Commons filename
    title = artifact_data.get('title', {}).get('sv', 'unknown_artifact')
    filename = f"Digitalt_Museum_{artifact_data['id']}_{secure_filename(title)}.jpg"
    session['commons_filename'] = filename
    
    # Prepare license info
    license_info = get_license_info(artifact_data)
    session['license_info'] = license_info
    
    return render_template('preview.html',
                         artifact=artifact_data,
                         image_url=image_url,
                         filename=filename,
                         license_info=license_info)

@bp.route('/authorize')
def authorize():
    """Start OAuth authorization with Wikimedia Commons."""
    if 'artifact_data' not in session:
        flash('No artifact data found. Please start over.', 'error')
        return redirect(url_for('main.index'))
    
    try:
        uploader = WikimediaUploader()
        auth_url = uploader.get_authorization_url()
        session['oauth_token'] = uploader.oauth_token
        session['oauth_token_secret'] = uploader.oauth_token_secret
        
        return redirect(auth_url)
    except Exception as e:
        current_app.logger.error(f"OAuth authorization error: {str(e)}")
        flash('Error initiating OAuth authorization', 'error')
        return redirect(url_for('main.index'))

@bp.route('/oauth_callback')
def oauth_callback():
    """OAuth callback handler."""
    if 'oauth_token' not in session or 'oauth_token_secret' not in session:
        flash('OAuth session expired. Please start over.', 'error')
        return redirect(url_for('main.index'))
    
    oauth_verifier = request.args.get('oauth_verifier')
    if not oauth_verifier:
        flash('OAuth verification failed', 'error')
        return redirect(url_for('main.index'))
    
    try:
        uploader = WikimediaUploader(
            access_token=session['oauth_token'],
            access_token_secret=session['oauth_token_secret']
        )
        access_token, access_token_secret = uploader.get_access_token(oauth_verifier)
        
        # Store access tokens for upload
        session['wm_access_token'] = access_token
        session['wm_access_token_secret'] = access_token_secret
        
        # Clean up temporary OAuth tokens
        session.pop('oauth_token', None)
        session.pop('oauth_token_secret', None)
        
        return redirect(url_for('main.upload'))
    
    except Exception as e:
        current_app.logger.error(f"OAuth callback error: {str(e)}")
        flash('Error completing OAuth authorization', 'error')
        return redirect(url_for('main.index'))

@bp.route('/upload')
def upload():
    """Handle the actual upload to Wikimedia Commons."""
    if 'wm_access_token' not in session or 'wm_access_token_secret' not in session:
        return redirect(url_for('main.authorize'))
    
    artifact_data = session.get('artifact_data')
    image_url = session.get('image_url')
    filename = session.get('commons_filename')
    license_info = session.get('license_info')
    
    if not all([artifact_data, image_url, filename, license_info]):
        flash('Session data missing. Please start over.', 'error')
        return redirect(url_for('main.index'))
    
    try:
        # Download the image
        response = requests.get(image_url, stream=True)
        response.raise_for_status()
        image_data = response.content
        
        # Prepare metadata
        description = generate_commons_description(artifact_data, license_info)
        categories = generate_categories(artifact_data)
        structured_data = generate_structured_data(artifact_data)
        
        # Initialize uploader with access tokens
        uploader = WikimediaUploader(
            access_token=session['wm_access_token'],
            access_token_secret=session['wm_access_token_secret']
        )
        
        # Upload to Commons
        result = uploader.upload_to_commons(
            filename=filename,
            image_data=image_data,
            description=description,
            categories=categories,
            structured_data=structured_data
        )
        
        if result.get('upload', {}).get('result') == 'Success':
            commons_url = f"https://commons.wikimedia.org/wiki/File:{filename.replace(' ', '_')}"
            flash('Upload successful!', 'success')
            
            # Clean up session
            session.pop('artifact_data', None)
            session.pop('image_url', None)
            session.pop('commons_filename', None)
            session.pop('license_info', None)
            session.pop('wm_access_token', None)
            session.pop('wm_access_token_secret', None)
            
            return render_template('result.html',
                                success=True,
                                commons_url=commons_url,
                                filename=filename)
        else:
            error = result.get('error', {}).get('info', 'Unknown error')
            current_app.logger.error(f"Upload failed: {error}")
            return render_template('result.html',
                                success=False,
                                error=error)
    
    except Exception as e:
        current_app.logger.error(f"Upload error: {str(e)}")
        flash('Error uploading to Wikimedia Commons', 'error')
        return redirect(url_for('main.preview'))

def extract_artifact_id(url):
    """Extract artifact ID from Digitalt Museum URL."""
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split('/') if p]
    
    # Handle both formats: /id/title and /id/
    if len(path_parts) >= 1:
        return path_parts[-2] if path_parts[-1].isdigit() else path_parts[-1]
    raise ValueError("Invalid Digitalt Museum URL")

def get_license_info(artifact_data):
    """Determine license information from artifact data."""
    # Default to CC-BY-SA 4.0 if no license info found
    return {
        'template': '{{CC-BY-SA-4.0}}',
        'text': 'This file is made available under the Creative Commons CC-BY-SA 4.0 license by the institution.',
        'short': 'CC-BY-SA-4.0'
    }

def generate_commons_description(artifact_data, license_info):
    """Generate the file description for Wikimedia Commons."""
    title = artifact_data.get('title', {}).get('sv', 'Untitled artifact')
    creator = artifact_data.get('creator', {}).get('sv', 'Unknown creator')
    object_type = artifact_data.get('objectType', {}).get('sv', 'Unknown type')
    dating = artifact_data.get('dating', {}).get('sv', 'Undated')
    material = artifact_data.get('material', {}).get('sv', 'Unknown material')
    dimensions = artifact_data.get('dimensions', {}).get('sv', '')
    institution = artifact_data.get('owner', {}).get('name', {}).get('sv', 'Unknown institution')
    
    return f"""== {{{{int:filedesc}}}} ==
{{{{Artwork
| title       = {title}
| artist      = {creator}
| object type = {object_type}
| date        = {dating}
| medium      = {material}
| dimensions  = {dimensions}
| institution = {institution}
| accession number = {artifact_data['id']}
| source      = Digitalt Museum
| permission  = {license_info['text']}
}}}}

== {{{{int:license}}}} ==
{license_info['template']}

{{{{Digitalt Museum|{artifact_data['id']}}}}}"""

def generate_categories(artifact_data):
    """Generate categories for the Commons upload."""
    categories = [
        "Media contributed by Digitalt Museum",
        f"Images from {artifact_data.get('owner', {}).get('name', {}).get('sv', 'Unknown institution')}"
    ]
    
    # Add material/type specific categories if available
    material = artifact_data.get('material', {}).get('sv', '').lower()
    object_type = artifact_data.get('objectType', {}).get('sv', '').lower()
    
    if material:
        categories.append(f"{material} objects")
    if object_type:
        categories.append(object_type)
    
    return categories

def generate_structured_data(artifact_data):
    """Generate structured data for Commons."""
    statements = []
    
    # Title
    if 'title' in artifact_data and 'sv' in artifact_data['title']:
        statements.append({
            "mainsnak": {
                "snaktype": "value",
                "property": "P1476",
                "datavalue": {
                    "value": {
                        "text": artifact_data['title']['sv'],
                        "language": "sv"
                    },
                    "type": "monolingualtext"
                }
            },
            "type": "statement",
            "rank": "normal"
        })
    
    # Creator
    if 'creator' in artifact_data and 'sv' in artifact_data['creator']:
        statements.append({
            "mainsnak": {
                "snaktype": "value",
                "property": "P170",
                "datavalue": {
                    "value": artifact_data['creator']['sv'],
                    "type": "string"
                }
            },
            "type": "statement",
            "rank": "normal"
        })
    
    # Institution
    if 'owner' in artifact_data and 'name' in artifact_data['owner'] and 'sv' in artifact_data['owner']['name']:
        statements.append({
            "mainsnak": {
                "snaktype": "value",
                "property": "P195",
                "datavalue": {
                    "value": {
                        "entity-type": "item",
                        "numeric-id": get_institution_qid(artifact_data['owner']['name']['sv'])
                    },
                    "type": "wikibase-entityid"
                }
            },
            "type": "statement",
            "rank": "normal"
        })
    
    # Add more properties as needed
    
    return {
        "statements": statements
    }

def get_institution_qid(institution_name):
    """Get Wikidata QID for common Swedish institutions (simplified)."""
    # In a real implementation, this would query Wikidata
    institution_map = {
        'Nordiska museet': 'Q430695',
        'Statens historiska museum': 'Q842380',
        'Skoklosters slott': 'Q430682',
        # Add more mappings as needed
    }
    return institution_map.get(institution_name, '')