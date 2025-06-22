import requests
import os
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

# Your list of proxy URLs with authentication
# Format: "http://username:password@ip:port"
PROXIES_LIST_RAW = (
    "http://sffxfbzy:iiksvk8lgt46@198.23.239.134:6540,"
    "http://sffxfbzy:iiksvk8lgt46@207.244.217.165:6712,"
    "http://sffxfbzy:iiksvk8lgt46@107.172.163.27:6543,"
    "http://sffxfbzy:iiksvk8lgt46@23.94.138.75:6349,"
    "http://sffxfbzy:iiksvk8lgt46@216.10.27.159:6837,"
    "http://sffxfbzy:iiksvk8lgt46@136.0.207.84:6661,"
    "http://sffxfbzy:iiksvk8lgt46@64.64.118.149:6732,"
    "http://sffxfbzy:iiksvk8lgt46@142.147.128.93:6593,"
    "http://sffxfbzy:iiksvk8lgt46@104.239.105.125:6655,"
    "http://sffxfbzy:iiksvk8lgt46@173.0.9.70:5653"
)

# Split the raw string into a list of individual proxy URLs
PROXIES_URLS_CLEANED = [p.strip() for p in PROXIES_LIST_RAW.split(',') if p.strip()]

# Target URL for testing (e.g., Google or a known site)
TEST_URL = "https://www.google.com"
# A YouTube video ID that is known to have subtitles and is accessible (for an optional deeper test)
TEST_VIDEO_ID = "M4V_iCaAYRw" # Changed to the new video ID
# Timeout for each request in seconds
TIMEOUT = 10

def test_single_proxy(proxy_url, target_url):
    """
    Tests if a single proxy works by making a GET request to a target URL.
    """
    # Set environment variables for requests to use the proxy
    os.environ['HTTP_PROXY'] = proxy_url
    os.environ['HTTPS_PROXY'] = proxy_url
    
    try:
        print(f"Testing proxy: {proxy_url} against {target_url}...")
        response = requests.get(target_url, timeout=TIMEOUT)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        print(f"  SUCCESS! Status Code: {response.status_code}")
        return True
    except requests.exceptions.Timeout:
        print(f"  TIMEOUT: Proxy {proxy_url} took too long to respond.")
    except requests.exceptions.RequestException as e:
        print(f"  FAILED: Proxy {proxy_url} encountered an error: {e}")
    except Exception as e:
        print(f"  UNKNOWN ERROR: Proxy {proxy_url} encountered an unexpected error: {e}")
    finally:
        # Clear environment variables to avoid interfering with subsequent requests
        if 'HTTP_PROXY' in os.environ:
            del os.environ['HTTP_PROXY']
        if 'HTTPS_PROXY' in os.environ:
            del os.environ['HTTPS_PROXY']
    return False

def test_proxy_with_youtube_transcript_api(proxy_url, video_id):
    """
    Tests if a single proxy works with youtube_transcript_api.
    """
    # Set environment variables for requests to use the proxy
    os.environ['HTTP_PROXY'] = proxy_url
    os.environ['HTTPS_PROXY'] = proxy_url
    
    try:
        print(f"Testing proxy: {proxy_url} with youtube_transcript_api for video {video_id}...")
        # Note: The youtube_transcript_api library will now use the environment variables
        # It no longer needs the 'proxies' argument here.
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        if transcript_list:
            print(f"  SUCCESS! Found {len(transcript_list)} subtitle tracks.")
            for transcript in transcript_list[:2]: # Print first 2 for brevity
                print(f"    - {transcript.language} ({transcript.language_code})")
            return True
        else:
            print("  FAILED: No subtitle tracks found (or YouTube blocked it silently).")
            return False
    except requests.exceptions.Timeout:
        print(f"  TIMEOUT: Proxy {proxy_url} took too long to respond from YouTube.")
    except requests.exceptions.RequestException as e:
        print(f"  FAILED: Proxy {proxy_url} encountered a network/proxy error with YouTube: {e}")
    except TranscriptsDisabled:
        print(f"  FAILED: Subtitles are disabled for video {video_id}.")
    except NoTranscriptFound:
        print(f"  FAILED: No transcript found for video {video_id}.")
    except Exception as e:
        print(f"  UNKNOWN ERROR with YouTube API for proxy {proxy_url}: {e}")
    finally:
        # Clear environment variables
        if 'HTTP_PROXY' in os.environ:
            del os.environ['HTTP_PROXY']
        if 'HTTPS_PROXY' in os.environ:
            del os.environ['HTTPS_PROXY']
    return False

if __name__ == "__main__":
    print(f"Starting proxy test for {len(PROXIES_URLS_CLEANED)} proxies.")
    
    working_proxies = []

    if not PROXIES_URLS_CLEANED:
        print("No proxies found in the list. Please check PROXIES_LIST_RAW string.")

    for i, proxy in enumerate(PROXIES_URLS_CLEANED):
        print(f"\n--- Testing Proxy {i+1}/{len(PROXIES_URLS_CLEANED)} ---")
        # First, test against a general known website
        general_test_success = test_single_proxy(proxy, TEST_URL)
        
        if general_test_success:
            # If it works generally, then test against YouTube API
            youtube_test_success = test_proxy_with_youtube_transcript_api(proxy, TEST_VIDEO_ID)
            if youtube_test_success:
                working_proxies.append(proxy)
        else:
            print(f"Proxy {proxy} failed general test, skipping YouTube test.")

    print("\n--- Testing Complete ---")
    if working_proxies:
        print(f"\nFound {len(working_proxies)} potentially working proxies:")
        for wp in working_proxies:
            print(f"- {wp}")
        print("\nCopy these working proxies and use them for the PROXIES_LIST environment variable on Render.com.")
    else:
        print("\nNo working proxies found. You may need to obtain more reliable proxies (e.g., paid ones).")

