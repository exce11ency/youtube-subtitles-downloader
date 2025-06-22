# Import necessary modules from Flask for creating the web application and handling requests.
from flask import Flask, request, jsonify, render_template, send_file
# Import YouTubeTranscriptApi for fetching subtitles.
# Removed NoLanguagesFound as it might not be directly importable from the top-level package in some versions.
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
# Import os for reading environment variables.
import os
# Import io for handling in-memory files (important for sending text files without saving to disk).
import io
# Import requests to potentially use for proxy configuration if youtube_transcript_api needs it directly.
# While youtube_transcript_api handles proxies internally, having requests available is good for general HTTP.
import requests

# Initialize the Flask application.
# The `static_folder` and `template_folder` tell Flask where to find static files (like CSS/JS)
# and HTML templates, respectively. In our simple setup, both are in the current directory.
app = Flask(__name__, static_folder='.', template_folder='.')

# --- Proxy Configuration ---
# Read proxy settings from environment variables.
# This makes it easy to change proxies without modifying code and keeps them secure.
# PROXIES_LIST should be a comma-separated string of proxy URLs (e.g., "http://user:pass@ip:port,http://ip2:port2").
# For now, we'll use an empty list if not set, meaning no proxies will be used by default.
# You will set this variable on Render.com.
PROXIES_LIST = os.getenv('PROXIES_LIST', '').split(',')
# Clean up any empty strings from the split
PROXIES_LIST = [p.strip() for p in PROXIES_LIST if p.strip()]

# A simple way to rotate proxies (for demonstration). In a real app, you might use a more robust queue.
current_proxy_index = 0

def get_next_proxy():
    """
    Cycles through the list of proxies.
    Returns a dictionary formatted for requests (or youtube_transcript_api's proxy setting).
    """
    global current_proxy_index
    if not PROXIES_LIST:
        return None # No proxies configured
    
    proxy_url = PROXIES_LIST[current_proxy_index % len(PROXIES_LIST)]
    current_proxy_index += 1
    
    # youtube_transcript_api expects proxies in this format for its 'proxies' parameter:
    # {'http': 'http://your_proxy', 'https': 'https://your_proxy'}
    # Or for a single proxy string in an array for `get_transcript` function directly.
    return proxy_url

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

    try:
        # Get the next proxy from our list
        proxy = get_next_proxy()
        
        # Pass the proxy to youtube_transcript_api if available
        # The list_transcripts function accepts a 'proxies' parameter.
        # It expects a dictionary for requests proxies, but internally it might also handle a simple string.
        # For direct use with youtube_transcript_api, we often just need to pass the proxy string directly
        # if the library handles the session. Let's try passing it as a list, which the library expects
        # for a pool of proxies.
        
        # If proxy is available, pass it to youtube_transcript_api.
        # The youtube-transcript-api library's `list_transcripts` and `get_transcript` functions
        # can accept a `proxies` parameter which expects a list of proxy strings.
        # It will then cycle through these proxies.
        
        # Using a list of proxies, even if only one is provided, is the standard way for this library.
        proxies_for_lib = PROXIES_LIST if PROXIES_LIST else None

        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id, proxies=proxies_for_lib)
        
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

    try:
        # Get the next proxy from our list
        proxy = get_next_proxy()
        proxies_for_lib = PROXIES_LIST if PROXIES_LIST else None

        # Fetch the transcript for the specified video ID and language, using proxies if configured.
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang], proxies=proxies_for_lib)
        
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

# This ensures the Flask development server runs only when the script is executed directly.
if __name__ == '__main__':
    # Run the Flask app in debug mode. In production, you would use a production-ready WSGI server.
    app.run(debug=True)
```
**Changes in `app.py`:**

* **`data = request.get_json(silent=True)`**: Added `silent=True` to `get_json()`. This prevents an error if the request body is not valid JSON, instead returning `None`.
* **Debugging Prints**: Added `print(f"Received data type: {type(data)}")` and `print(f"Received data: {data}")` after `request.get_json()`. These will output the type and content of the received data to your Render logs, which will be crucial for debugging.
* **Type Validation**: Added `if not isinstance(data, dict):` to explicitly check if `data` is a dictionary. If it's not, it will return a more informative error message to the frontend, preventing the `'list' object has no attribute 'get'` crash.

**Next Steps for you:**

1.  **Save the updated `app.py`**: Make sure your local `app.py` file is updated with this new content.
2.  **Commit and Push to GitHub**:
    Open your terminal in your project folder and run:
    ```bash
    git add .
    git commit -m "Add debugging and robust type checking for request data"
    git push origin main
    ```
3.  **Render will automatically redeploy**: Once the new commit is on GitHub, Render.com should detect the change and start a new deployment. Monitor the logs on Render.com to ensure this deployment completes successfully (status "Live").

After the deployment, **the most crucial step** remains: **you must provide working proxy addresses in the `PROXIES_LIST` environment variable on Render.com**. If this variable is empty or contains non-working proxies, the YouTube blocking error will persist.

Once your service is "Live" again after this fix and you have a `PROXIES_LIST` set with working proxies, try fetching subtitles from your deployed service at `https://sub-dl-1tzt.onrender.com`. Then, check the Render logs again to see the output of the new `print` statements and any new erro