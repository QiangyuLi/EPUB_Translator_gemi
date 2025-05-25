import zipfile
import os
import re
import json
import shutil
from bs4 import BeautifulSoup
import google.generativeai as genai
import time
import argparse
from google.api_core import exceptions as google_api_exceptions
import hashlib
import itertools

# --- Configuration ---
MODEL_NAME = "gemini-2.0-flash-lite"

# Reverted to a simpler, less restrictive default translation prompt.
DEFAULT_TRANSLATION_PROMPT = """
Translate the following content into Simplified Chinese **only if the text clearly consists of meaningful, natural language** — such as full sentences, phrases, documentation, or conversational content.
Do **not translate** or modify the input if it meets **any** of the following conditions:
- It is structured content such as XML, HTML, JSON, or programming code.
- It contains markup, configuration, commands, paths, keys, tags, or variable names.
- It is composed only of symbols, placeholders, punctuation (e.g., ——— or ***), or lacks any semantic meaning.
- It is an isolated number, acronym, abbreviation, or Roman numeral without context.
- It is ambiguous or contextless and cannot be reliably identified as human language.
If the text **does not meet the criteria for confident, accurate translation**, return it **exactly as received**, with **no modifications**, **no formatting**, and **no added or invented content**.
Do **not include** any introductory text, explanation, or labels. Output only the translated text, or the original text unchanged if translation is not applicable.
"""

# Global variable to hold the current model instance and API key list
_current_model = None
_api_keys = []
_api_key_iterator = None

def setup_gemini_api(api_key):
    """Sets up the Google Gemini API with the provided key."""
    try:
        genai.configure(api_key=api_key)
        global _current_model
        _current_model = genai.GenerativeModel(MODEL_NAME)
        print(f"Gemini API configured successfully with key: {api_key[:5]}...")
        return True
    except Exception as e:
        print(f"Error configuring Gemini API with key {api_key[:5]}...: {e}")
        return False

def get_next_api_key_and_setup(is_initial_setup=False):
    """
    Cycles to the next API key and sets up the Gemini API.
    Returns True on success, False if no more keys or all failed *in the current pass*.
    If is_initial_setup is True, it tries all keys once without strict rate limit handling from translate_text.
    """
    global _api_key_iterator
    global _api_keys

    if not _api_keys:
        print("Error: No API keys available to cycle through.")
        return False
    
    if _api_key_iterator is None:
        _api_key_iterator = itertools.cycle(_api_keys)

    # We'll try all keys once in this function call
    for _ in range(len(_api_keys)):
        next_key = next(_api_key_iterator)
        if setup_gemini_api(next_key):
            return True
    
    # If we reached here, it means all keys failed to set up or were rate-limited in this cycle.
    return False

def is_meaningful_text(text):
    """
    Checks if a string is likely meaningful natural language,
    filtering out lines that are just symbols, numbers, or whitespace.
    """
    if not text.strip(): # Check for empty or purely whitespace strings
        return False
    
    # Check if the text consists predominantly of non-alphanumeric characters or digits
    if re.search(r'[\u4e00-\u9fffA-Za-z]', text):
        alphanum_chars = sum(c.isalnum() for c in text)
        total_chars = len(text)
        # Consider texts with very low alphanumeric content as potentially not meaningful
        if total_chars > 0 and (alphanum_chars / total_chars) < 0.15: # Adjusted threshold slightly
            # Additional check for repetitive symbols that might contain a single letter (e.g., "----A----")
            if re.fullmatch(r'([-\*=/_#\.])+\s*[A-Za-z]?\s*([-\*=/_#\.])+', text.strip()):
                return False
            return True
        return True # If it has enough alphanumeric characters, consider it meaningful
    
    # Consider if the text is just repeating patterns of symbols or numbers.
    if re.fullmatch(r'([-\*=/_#\.])\1+', text.strip()) or re.fullmatch(r'\d[\d\s\.]*', text.strip()):
        return False
        
    return False # Default to false if no meaningful content detected by basic checks

def translate_text(text_content, base_prompt):
    """
    Translates a given text content into Simplified Chinese using the Gemini API.
    Returns (translated_text, True) on success, (original_text, False) on persistent failure
    (meaning the translation should be skipped and original content kept).
    Includes explicit rate limit handling (waiting and API key cycling).
    """
    if not text_content.strip():
        return "", True
    
    # Pre-translation Filtering for non-meaningful text:
    # If the text is deemed not meaningful, return original content immediately.
    if not is_meaningful_text(text_content):
        print(f"  Skipping non-meaningful text (pre-filter): {text_content[:70]}{'...' if len(text_content) > 70 else ''}")
        return text_content, True # Successfully "processed" by returning original

    prompt = f"{base_prompt}{text_content}"
    max_retries_per_key = 2 # Retries within the same API key before trying the next one
    initial_wait_time_on_error = 2 # seconds for general errors
    wait_time_on_all_keys_exhausted = 60 # seconds to wait when all keys hit rate limit

    global _current_model
    global _api_keys

    # Outer loop to handle persistent rate limits across all keys
    while True: # Loop indefinitely until translation succeeds or a critical non-rate-limit error occurs
        if _current_model is None:
            # Attempt to set up a model if none is active (e.g., first run or previous key failed setup)
            if not get_next_api_key_and_setup():
                print("Critical: No active Gemini model available and all keys failed to set up. Cannot translate this segment.")
                return text_content, False # Cannot proceed at all

        # Inner loop for retries with the current API key
        for attempt in range(max_retries_per_key):
            try:
                response = _current_model.generate_content(prompt)

                if response and response.text:
                    translated_text = response.text.strip()
                    print(f"  Original: {text_content[:70]}{'...' if len(text_content) > 70 else ''}")
                    print(f"  Translated: {translated_text[:70]}{'...' if len(translated_text) > 70 else ''}\n")
                    return translated_text, True
                else:
                    print(f"Attempt {attempt + 1} (current key): No translation found in API response for text: '{text_content[:50]}...'")
                    if attempt < max_retries_per_key - 1:
                        wait_time = initial_wait_time_on_error * (2 ** attempt)
                        print(f"  Waiting {wait_time} seconds before retrying with current key...")
                        time.sleep(wait_time)
                    else:
                        print("  Max retries reached with current key. Trying next API key if available.")
                        break # Break inner loop, try next API key via outer loop's cycle logic
            except google_api_exceptions.ResourceExhausted as e:
                print(f"Attempt {attempt + 1} (current key): Rate limit exceeded for text: '{text_content[:50]}...'")
                print("  Switching to next API key...")
                # Try next API key immediately
                if not get_next_api_key_and_setup():
                    # All keys are rate-limited. Now, we wait.
                    print(f"All API keys are currently rate-limited. Waiting {wait_time_on_all_keys_exhausted} seconds before retrying all keys.")
                    time.sleep(wait_time_on_all_keys_exhausted)
                    # After waiting, try to get a new key again
                    continue # Continue the outer loop to retry getting a new key and translation
                break # Break inner loop, outer loop will continue with new key
            except Exception as e:
                print(f"Attempt {attempt + 1} (current key): General API error: {e} for text: '{text_content[:50]}...'")
                if attempt < max_retries_per_key - 1:
                    wait_time = initial_wait_time_on_error * (2 ** attempt)
                    print(f"  Waiting {wait_time} seconds due to error before retrying with current key...")
                    time.sleep(wait_time)
                else:
                    print("  Max retries reached with current key due to errors. Trying next API key if available.")
                    # If general errors persist with current key, try next key.
                    # If this fails to set up a new key, it will eventually fall into the 'all keys rate-limited' logic or critical error.
                    if not get_next_api_key_and_setup():
                        print(f"Critical: All API keys exhausted or failed during general errors. Cannot translate: '{text_content[:50]}...'")
                        return text_content, False # Critical failure, return original
                    break # Break inner loop, outer loop will continue with new key
        
        # If inner loop finished without returning (meaning max retries per key reached or switched key)
        # and we are still in the outer loop, it implies we need to try next key or wait.
        # The 'continue' in the ResourceExhausted block handles the waiting.
        # If we broke from inner loop due to max_retries_per_key and successfully got new key,
        # the outer loop will just continue with the new key.
        pass # This pass is just to make the while True loop explicit.

def extract_epub(epub_path, extract_to_dir):
    """Extracts the contents of an EPUB file."""
    try:
        with zipfile.ZipFile(epub_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to_dir)
        print(f"EPUB extracted to: {extract_to_dir}")
        return True
    except Exception as e:
        print(f"Error extracting EPUB: {e}")
        return False

def find_html_files(directory):
    """Finds all HTML/XHTML files in the extracted EPUB directory."""
    html_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(('.html', '.xhtml', '.htm')):
                html_files.append(os.path.join(root, file))
    return html_files

def translate_html_file(file_path, base_prompt, translation_status_dict, translation_cache):
    """
    Reads an HTML file, translates its text content, and writes the modified content back.
    Updates the translation_status_dict based on success/failure within the file.
    Includes logic to use and update the translation_cache for sentence-level progress.
    """
    file_had_errors = False
    file_relative_path = os.path.relpath(file_path, os.path.commonpath([file_path, os.path.dirname(file_path)]))

    if file_relative_path not in translation_cache:
        translation_cache[file_relative_path] = {}

    try:
        with open(file_path, 'rb') as f:
            content_bytes = f.read()

        parser_name = 'html.parser'
        try:
            import lxml
            parser_name = 'lxml'
        except ImportError:
            pass

        try:
            soup = BeautifulSoup(content_bytes, parser_name)
        except Exception as e:
            print(f"Error parsing {os.path.basename(file_path)} with '{parser_name}': {e}. Attempting with 'html.parser'.")
            try:
                soup = BeautifulSoup(content_bytes, 'html.parser')
            except Exception as inner_e:
                print(f"Critical: Failed to parse {os.path.basename(file_path)} even with 'html.parser': {inner_e}. Skipping file.")
                translation_status_dict[file_path] = "failed"
                return False

        for text_node in soup.find_all(string=True):
            if text_node.parent.name not in ['script', 'style', 'title', 'meta', 'link', 'head', 'noscript', 'code']:
                original_text = str(text_node).strip()
                
                if original_text:
                    text_hash = hashlib.sha256(original_text.encode('utf-8')).hexdigest()

                    if text_hash in translation_cache[file_relative_path]:
                        translated_text = translation_cache[file_relative_path][text_hash]
                        print(f"  Reusing cached translation for: {original_text[:70]}{'...' if len(original_text) > 70 else ''}")
                        print(f"  Cached: {translated_text[:70]}{'...' if len(translated_text) > 70 else ''}\n")
                    else:
                        translated_text, success = translate_text(original_text, base_prompt)
                        if not success:
                            file_had_errors = True
                        
                        if translated_text:
                            translation_cache[file_relative_path][text_hash] = translated_text

                    if translated_text:
                        text_node.replace_with(translated_text)

        with open(file_path, 'wb') as f:
            f.write(soup.encode('utf-8'))

        if file_had_errors:
            translation_status_dict[file_path] = "failed"
            print(f"Finished processing: {os.path.basename(file_path)} (Some segments failed)\n")
        else:
            translation_status_dict[file_path] = "completed"
            print(f"Finished processing: {os.path.basename(file_path)} (All segments successful)\n")
        return True
    except Exception as e:
        print(f"Critical error processing HTML file {file_path}: {e}")
        translation_status_dict[file_path] = "failed"
        return False

def create_translated_epub(source_dir, output_epub_path):
    """Creates a new EPUB file from the modified contents."""
    try:
        mimetype_path = os.path.join(source_dir, 'mimetype')
        if not os.path.exists(mimetype_path):
            print("Error: mimetype file not found. Cannot create EPUB.")
            return False

        with zipfile.ZipFile(output_epub_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(mimetype_path, 'mimetype', compress_type=zipfile.ZIP_STORED)

            for root, dirs, files in os.walk(source_dir):
                for file in files:
                    if file == 'mimetype':
                        continue
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, source_dir)
                    zf.write(file_path, arcname)
        print(f"Translated EPUB created at: {output_epub_path}")
        return True
    except Exception as e:
        print(f"Error creating translated EPUB: {e}")
        return False

def cleanup_temp_dir(temp_dir):
    """Removes the temporary directory."""
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
        print(f"Cleaned up temporary directory: {temp_dir}")

# --- Main Command-Line Process ---

def main():
    parser = argparse.ArgumentParser(
        description="Translate an EPUB file into Simplified Chinese using Google Gemini API."
    )
    parser.add_argument(
        "epub_file_path",
        help="Path to the EPUB file to be translated."
    )
    parser.add_argument(
        "--api_keys",
        nargs='+',
        help="One or more Google Gemini API Keys, separated by spaces. E.g., --api_keys KEY1 KEY2 KEY3. Will be used in a loop."
    )
    parser.add_argument(
        "--output_dir",
        default=".",
        help="Directory to save the translated EPUB. Defaults to current directory."
    )
    parser.add_argument(
        "--temp_dir",
        help="Optional: Specific directory to extract EPUB contents and manage translation status. Defaults to a dynamically named folder in the current directory."
    )
    parser.add_argument(
        "--prompt_file",
        help="Path to a .txt file containing the custom translation prompt. Overrides the default prompt."
    )

    args = parser.parse_args()

    global _api_keys
    if args.api_keys:
        _api_keys = args.api_keys
        print(f"Using {len(_api_keys)} API Key(s) from command line arguments.")
    else:
        env_api_key = os.getenv("GOOGLE_API_KEY")
        if env_api_key:
            _api_keys = [env_api_key]
            print("Using API Key from GOOGLE_API_KEY environment variable.")
        else:
            print("Error: No API Key(s) provided. Please use --api_keys KEY1 KEY2... or set GOOGLE_API_KEY environment variable.")
            return
    
    if not _api_keys:
        print("Error: No valid API keys found. Exiting.")
        return

    # Initial API setup attempt
    if not get_next_api_key_and_setup(is_initial_setup=True): # Use is_initial_setup flag
        print("Failed to set up any Gemini API key initially. Please check your keys or network. Exiting.")
        return

    translation_base_prompt = DEFAULT_TRANSLATION_PROMPT
    if args.prompt_file:
        try:
            with open(args.prompt_file, 'r', encoding='utf-8') as f:
                custom_prompt_content = f.read().strip()
                if custom_prompt_content:
                    translation_base_prompt = custom_prompt_content + "\n\n"
                    print(f"Using custom prompt from: {args.prompt_file}")
                else:
                    print(f"Warning: Prompt file '{args.prompt_file}' is empty. Using default prompt.")
        except FileNotFoundError:
            print(f"Warning: Prompt file '{args.prompt_file}' not found. Using default prompt.")
        except Exception as e:
            print(f"Warning: Could not read prompt file '{args.prompt_file}': {e}. Using default prompt.")
    else:
        print("Using default translation prompt.")

    epub_path = os.path.abspath(args.epub_file_path)
    if not os.path.exists(epub_path):
        print(f"Error: EPUB file not found at '{epub_path}'")
        return
    if not epub_path.lower().endswith(".epub"):
        print(f"Error: The provided file '{epub_path}' does not appear to be an EPUB file.")
        return

    epub_filename = os.path.basename(epub_path)
    epub_name_without_ext = os.path.splitext(epub_filename)[0]

    if args.temp_dir:
        temp_dir = os.path.abspath(args.temp_dir)
        print(f"Using specified temporary directory: {temp_dir}")
    else:
        temp_dir = os.path.join(os.getcwd(), f'temp_epub_translation_{epub_name_without_ext}')
        print(f"Using default temporary directory: {temp_dir}")

    output_epub_filename = f"{epub_name_without_ext}_zh-Hans.epub"
    output_epub_path = os.path.join(os.path.abspath(args.output_dir), output_epub_filename)
    
    status_file_path = os.path.join(temp_dir, f'{epub_name_without_ext}_file_status.json')
    cache_file_path = os.path.join(temp_dir, f'{epub_name_without_ext}_translation_cache.json')

    os.makedirs(os.path.abspath(args.output_dir), exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

    translation_status = {}
    translation_cache = {}

    if os.path.exists(status_file_path):
        try:
            with open(status_file_path, 'r', encoding='utf-8') as f:
                translation_status = json.load(f)
            print(f"Loaded previous file-level translation status from: {status_file_path}")
        except json.JSONDecodeError:
            print(f"Warning: Could not read file-level translation status file '{status_file_path}'. Starting fresh for this EPUB.")
        except Exception as e:
            print(f"Warning: Error loading file-level translation status: {e}. Starting fresh for this EPUB.")
    
    if os.path.exists(cache_file_path):
        try:
            with open(cache_file_path, 'r', encoding='utf-8') as f:
                translation_cache = json.load(f)
            print(f"Loaded previous sentence-level translation cache from: {cache_file_path}")
        except json.JSONDecodeError:
            print(f"Warning: Could not read sentence-level translation cache file '{cache_file_path}'. Starting fresh for this EPUB.")
        except Exception as e:
            print(f"Warning: Error loading sentence-level translation cache: {e}. Starting fresh for this EPUB.")


    print(f"\n--- Starting EPUB Translation for '{epub_filename}' ---")
    print(f"Using model: {MODEL_NAME}")
    print(f"Temporary directory: {temp_dir}")
    print(f"Output EPUB will be saved to: {output_epub_path}")

    if not os.path.exists(temp_dir) or not os.listdir(temp_dir):
         print(f"Temporary directory '{temp_dir}' is empty or does not exist. Extracting EPUB.")
         if not extract_epub(epub_path, temp_dir):
             cleanup_temp_dir(temp_dir)
             return
    else:
        print(f"Temporary directory '{temp_dir}' already exists with files. Re-using for incremental translation.")

    try:
        html_files = find_html_files(temp_dir)
        if not html_files:
            print("No HTML/XHTML files found in the EPUB. Nothing to translate.")
            return

        print(f"Found {len(html_files)} HTML files in EPUB structure.")
        reprocessed_files_count = 0
        skipped_files_count = 0

        for i, html_file_abs_path in enumerate(html_files):
            html_file_rel_path = os.path.relpath(html_file_abs_path, temp_dir)

            current_file_status = translation_status.get(html_file_rel_path, "pending")

            if current_file_status == "completed":
                print(f"Skipping already completed file {i+1}/{len(html_files)}: {os.path.basename(html_file_abs_path)}")
                skipped_files_count += 1
                continue

            print(f"\n--- Translating file {i+1}/{len(html_files)}: {os.path.basename(html_file_abs_path)} --- (Status: {current_file_status})")
            if translate_html_file(html_file_abs_path, translation_base_prompt, translation_status, translation_cache):
                reprocessed_files_count += 1
            
            with open(status_file_path, 'w', encoding='utf-8') as f:
                json.dump(translation_status, f, indent=4)
            
            with open(cache_file_path, 'w', encoding='utf-8') as f:
                json.dump(translation_cache, f, indent=4, ensure_ascii=False)

        print(f"\nProcessed {reprocessed_files_count} files, skipped {skipped_files_count} already completed files.")

        if create_translated_epub(temp_dir, output_epub_path):
            print(f"\nTranslation complete! Translated EPUB saved to: {output_epub_path}")
        else:
            print("\nFailed to create the translated EPUB.")

    finally:
        all_completed = all(status == "completed" for status in translation_status.values())
        if all_completed and os.path.exists(temp_dir) and os.path.exists(status_file_path) and os.path.exists(cache_file_path):
            cleanup_temp_dir(temp_dir)
            print(f"Cleaned up temporary directory: {temp_dir}")
        else:
            print(f"\nTemporary directory '{temp_dir}', file status '{status_file_path}', and sentence cache '{cache_file_path}' preserved for incremental translation (some files may still be 'failed' or 'pending').")

        print("\n--- Translation Process Finished ---")

# --- Run the script ---
if __name__ == "__main__":
    main()