import requests
import os
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

# Ваш список прокси URL с аутентификацией
# Формат: "http://username:password@hostname:port"
PROXIES_LIST_RAW = (
    "http://rRgXSIZv9R_0:bBmidIzItM1y@mg-26590.sp1.ovh:11001"
)

# Разделить строку на список отдельных прокси URL
PROXIES_URLS_CLEANED = [p.strip() for p in PROXIES_LIST_RAW.split(',') if p.strip()]

# Целевой URL для тестирования (например, Google или известный сайт)
TEST_URL = "https://www.google.com"
# ID видео YouTube, которое известно, что имеет субтитры и доступно
TEST_VIDEO_ID = "M4V_iCaAYRw"
# Таймаут для каждого запроса в секундах
TIMEOUT = 10

def test_single_proxy(proxy_url, target_url):
    """
    Проверяет, работает ли один прокси, отправляя GET-запрос на целевой URL.
    """
    # Установить переменные окружения для requests, чтобы использовать прокси
    os.environ['HTTP_PROXY'] = proxy_url
    os.environ['HTTPS_PROXY'] = proxy_url
    
    try:
        print(f"Testing proxy: {proxy_url} against {target_url}...")
        response = requests.get(target_url, timeout=TIMEOUT)
        response.raise_for_status() # Вызовет HTTPError для плохих ответов (4xx или 5xx)
        print(f"  SUCCESS! Status Code: {response.status_code}")
        return True
    except requests.exceptions.Timeout:
        print(f"  TIMEOUT: Proxy {proxy_url} took too long to respond.")
    except requests.exceptions.RequestException as e:
        print(f"  FAILED: Proxy {proxy_url} encountered an error: {e}")
    except Exception as e:
        print(f"  UNKNOWN ERROR: Proxy {proxy_url} encountered an unexpected error: {e}")
    finally:
        # Очистить переменные окружения, чтобы избежать помех для последующих запросов
        if 'HTTP_PROXY' in os.environ:
            del os.environ['HTTP_PROXY']
        if 'HTTPS_PROXY' in os.environ:
            del os.environ['HTTPS_PROXY']
    return False

def test_proxy_with_youtube_transcript_api(proxy_url, video_id):
    """
    Проверяет, работает ли один прокси с youtube_transcript_api.
    """
    # Установить переменные окружения для requests, чтобы использовать прокси
    os.environ['HTTP_PROXY'] = proxy_url
    os.environ['HTTPS_PROXY'] = proxy_url
    
    try:
        print(f"Testing proxy: {proxy_url} with youtube_transcript_api for video {video_id}...")
        # Примечание: Библиотека youtube_transcript_api теперь будет использовать переменные окружения
        # Ей больше не нужен аргумент 'proxies' здесь.
        
        # Получаем объект TranscriptList.
        transcript_list_obj = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Преобразуем TranscriptList в обычный список, чтобы можно было проверить его длину.
        transcript_list = list(transcript_list_obj) 
        
        if transcript_list:
            print(f"  SUCCESS! Found {len(transcript_list)} subtitle tracks.")
            for transcript in transcript_list[:2]: # Вывести первые 2 для краткости
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
        # Очистить переменные окружения
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
        # Сначала протестировать на общем известном веб-сайте
        general_test_success = test_single_proxy(proxy, TEST_URL)
        
        if general_test_success:
            # Если работает в целом, то протестировать на YouTube API
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
        print("\nСкопируйте эти рабочие прокси и используйте их для переменной окружения PROXIES_LIST на Render.com.")
    else:
        print("\nРабочих прокси не найдено. Возможно, вам потребуется приобрести более надежные прокси (например, платные).")
