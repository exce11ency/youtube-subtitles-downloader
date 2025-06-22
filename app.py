# Import necessary modules from Flask for creating the web application and handling requests.
from flask import Flask, request, jsonify, render_template, send_file
# Import YouTubeTranscriptApi for fetching subtitles.
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
# Import os for reading environment variables.
import os
# Import io for handling in-memory files (important for sending text files without saving to disk).
import io
# Import requests for general HTTP handling, though youtube_transcript_api uses it internally.
import requests

# Initialize the Flask application.
# The `static_folder` and `template_folder` tell Flask where to find static files (like CSS/JS)
# and HTML templates, respectively. In our simple setup, both are in the current directory.
# Corrected: 'template_template_folder' was a typo, changed to 'template_folder'.
app = Flask(__name__, static_folder='.', template_folder='.')

# --- Proxy Configuration ---
# Read proxy settings from environment variables.
# PROXIES_LIST should be a comma-separated string of proxy URLs (e.g., "http://user:pass@ip:port,http://ip2:port2").
# For now, we'll use an empty list if not set.
PROXIES_LIST_RAW = os.getenv('PROXIES_LIST', '').split(',')
# Clean up any empty strings from the split and ensure they are valid.
# These are the raw proxy strings to be used.
PROXIES_URLS_CLEANED = [p.strip() for p in PROXIES_LIST_RAW if p.strip()]

# Counter to cycle through proxies
current_proxy_index = 0

def set_global_proxy_env(proxy_url):
    """Sets HTTP_PROXY and HTTPS_PROXY environment variables."""
    os.environ['HTTP_PROXY'] = proxy_url
    os.environ['HTTPS_PROXY'] = proxy_url
    print(f"Set environment proxies to: {proxy_url}")

def clear_global_proxy_env():
    """Clears HTTP_PROXY and HTTPS_PROXY environment variables."""
    if 'HTTP_PROXY' in os.environ:
        del os.environ['HTTP_PROXY']
    if 'HTTPS_PROXY' in os.environ:
        del os.environ['HTTPS_PROXY']
    print("Cleared environment proxies.")


# Define a route for the homepage.
# When a user accesses the root URL ("/"), this function will be executed,
# and it will render the `index.html` file.
@app.route('/')
def index():
    """
    Renders the main index.html page when the root URL is accessed.
    """
    return render_template('index.html')

# Define an API endpoint to fetch available subtitles for a given YouTube video ID.
# This endpoint will handle POST requests, which is typical for data submission.
@app.route('/api/fetch_subtitles', methods=['POST'])
def fetch_subtitles():
    """
    Fetches available subtitle tracks for a YouTube video ID.
    Expects a JSON payload with 'videoId'.
    Returns a JSON response with available subtitle tracks or an error message.
    """
    # Get the JSON data from the request body.
    data = request.get_json(silent=True) # Use silent=True to avoid error if JSON is malformed/empty
    
    # --- Debugging additions ---
    print(f"Received data type: {type(data)}")
    print(f"Received data: {data}")
    # --- End debugging additions ---

    # Validate that data is a dictionary before trying to access 'videoId'
    if not isinstance(data, dict):
        return jsonify({"success": False, "message": "Invalid request payload. Expected a JSON object."}), 400

    # Extract the 'videoId' from the received data.
    video_id = data.get('videoId')

    # Basic validation: Check if videoId is provided.
    if not video_id:
        return jsonify({"success": False, "message": "Video ID is required"}), 400

    # --- Proxy application logic ---
    global current_proxy_index
    selected_proxy = None
    if PROXIES_URLS_CLEANED:
        selected_proxy = PROXIES_URLS_CLEANED[current_proxy_index % len(PROXIES_URLS_CLEANED)]
        current_proxy_index += 1 # Move to the next proxy for the next request
    
    try:
        if selected_proxy:
            set_global_proxy_env(selected_proxy) # Set proxy for this request
        
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id) # No 'proxies' arg here
        
        # Prepare a list to store information about each available subtitle track.
        available_subtitles = []
        for transcript in transcript_list:
            # Append details for each transcript, including language code, language name,
            # whether it's auto-generated, and whether it's translatable.
            available_subtitles.append({
                "lang": transcript.language_code,
                "name": transcript.language,
                "is_auto_generated": transcript.is_generated,
                "is_translatable": transcript.is_translatable
            })
        
        # Return a success response with the list of available subtitles.
        return jsonify({"success": True, "subtitles": available_subtitles}), 200

    # Handle specific exceptions from youtube_transcript_api for better error reporting.
    except TranscriptsDisabled:
        return jsonify({"success": False, "message": "Subtitles are disabled for this video."}), 404
    except NoTranscriptFound: # This exception usually covers cases where no languages are found either.
        return jsonify({"success": False, "message": "No subtitles found for this video (or they are not public/available)."}), 404
    except requests.exceptions.RequestException as e:
        # Catch requests-related errors, often indicative of proxy issues or network problems.
        print(f"Network or proxy error fetching subtitles: {e}")
        return jsonify({"success": False, "message": "A network or proxy error occurred. Please try again or check proxy settings."}), 503
    except Exception as e:
        # Catch any other unexpected errors and return a generic error message.
        print(f"Error fetching subtitles: {e}") # Log the error for debugging
        return jsonify({"success": False, "message": "An unexpected error occurred while fetching subtitle info."}), 500
    finally:
        # --- Ensure proxies are cleared after the request ---
        clear_global_proxy_env()

# Define an API endpoint to download specific subtitles.
# This endpoint expects a GET request with 'videoId', 'lang', and 'format'.
@app.route('/api/download_subtitle', methods=['GET'])
def download_subtitle():
    """
    Downloads a specific subtitle track for a YouTube video ID in a given format.
    Expects 'videoId', 'lang', and 'format' as query parameters.
    Returns the subtitle content as a file download.
    """
    # Get query parameters from the request URL.
    video_id = request.args.get('videoId')
    lang = request.args.get('lang')
    file_format = request.args.get('format', 'srt') # Default to srt if format is not specified

    # Basic validation for required parameters.
    if not video_id or not lang:
        return jsonify({"success": False, "message": "Video ID and language are required"}), 400

    # --- Proxy application logic for download ---
    global current_proxy_index
    selected_proxy = None
    if PROXIES_URLS_CLEANED:
        selected_proxy = PROXIES_URLS_CLEANED[current_proxy_index % len(PROXIES_URLS_CLEANED)]
        current_proxy_index += 1 # Move to the next proxy for the next request

    try:
        if selected_proxy:
            set_global_proxy_env(selected_proxy) # Set proxy for this request

        # Fetch the transcript for the specified video ID and language, using proxies if configured.
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang]) # No 'proxies' arg here
        
        # Initialize an empty string to build the subtitle content.
        subtitle_content = ""

        # Format the subtitle content based on the requested file_format.
        if file_format == 'txt':
            # For TXT, simply concatenate all text.
            for entry in transcript:
                subtitle_content += f"{entry['text']}\n"
            mimetype = "text/plain"
            filename = f"{video_id}_{lang}.txt"
        elif file_format == 'srt':
            # For SRT, format with timestamps and sequence numbers.
            for i, entry in enumerate(transcript):
                start_ms = int(entry['start'] * 1000)
                end_ms = int((entry['start'] + entry['duration']) * 1000)

                # Helper to format milliseconds into HH:MM:SS,MS
                def format_timestamp(ms):
                    hours = ms // 3_600_000
                    ms %= 3_600_000
                    minutes = ms // 60_000
                    ms %= 60_000
                    seconds = ms // 1_000
                    milliseconds = ms % 1_000
                    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

                subtitle_content += f"{i + 1}\n" # Sequence number
                subtitle_content += f"{format_timestamp(start_ms)} --> {format_timestamp(end_ms)}\n"
                subtitle_content += f"{entry['text']}\n\n"
            mimetype = "application/x-subrip" # Standard MIME type for SRT
            filename = f"{video_id}_{lang}.srt"
        else:
            # Handle unsupported formats.
            return jsonify({"success": False, "message": "Unsupported format. Only 'txt' and 'srt' are supported."}), 400

        # Create an in-memory file-like object from the subtitle content.
        buffer = io.BytesIO(subtitle_content.encode('utf-8'))
        
        # Send the file to the client for download.
        return send_file(buffer, mimetype=mimetype, as_attachment=True, download_name=filename)

    except NoTranscriptFound:
        return jsonify({"success": False, "message": "No subtitles found for this video (or they are not public/available)."}), 404
    except TranscriptsDisabled:
        return jsonify({"success": False, "message": "Subtitles are disabled for this video."}), 404
    except requests.exceptions.RequestException as e:
        print(f"Network or proxy error downloading subtitle: {e}")
        return jsonify({"success": False, "message": "A network or proxy error occurred during download. Please try again or check proxy settings."}), 503
    except Exception as e:
        # Catch any errors during the download process.
        print(f"Error downloading subtitle: {e}") # Log the error for debugging
        return jsonify({"success": False, "message": "An unexpected error occurred while downloading the subtitle."}), 500
    finally:
        # --- Ensure proxies are cleared after the request ---
        clear_global_proxy_env()

# This ensures the Flask development server runs only when the script is executed directly.
if __name__ == '__main__':
    # Run the Flask app in debug mode. In production, you would use a production-ready WSGI server.
    app.run(debug=True)
