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
# --- Helper Functions ---

def setup_gemini_api(api_key):
    """Sets up the Google Gemini API with the provided key."""
    if not api_key:
        print("Error: Gemini API Key is missing. Please provide it via --api_key or set the GOOGLE_API_KEY environment variable.")
        return False
    try:
        genai.configure(api_key=api_key)
        print("Gemini API configured successfully.")
        return True
    except Exception as e:
        print(f"Error configuring Gemini API: {e}")
        return False

def translate_text(text_content, model, base_prompt):
    """
    Translates a given text content into Simplified Chinese using the Gemini API.
    Returns (translated_text, True) on success, (original_text, False) on persistent failure.
    Includes explicit rate limit handling (waiting).
    """
    if not text_content.strip():
        return "", True # Successfully processed empty text

    prompt = f"{base_prompt}{text_content}"
    max_retries = 5 # Increased retries for robustness against rate limits
    initial_wait_time = 2 # seconds

    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)

            if response and response.text:
                translated_text = response.text.strip() # Strip whitespace from translation too
                
                print(f"  Original: {text_content[:70]}{'...' if len(text_content) > 70 else ''}")
                print(f"  Translated: {translated_text[:70]}{'...' if len(translated_text) > 70 else ''}\n")
                return translated_text, True # Return translated text and success flag
            else:
                print(f"Attempt {attempt + 1}: No translation found in API response for text: '{text_content[:50]}...'")
                if attempt < max_retries - 1:
                    wait_time = initial_wait_time * (2 ** attempt)
                    print(f"  Waiting {wait_time} seconds before retrying...")
                    time.sleep(wait_time)
                else:
                    print("Max retries reached. Skipping translation for this segment.")
                    return text_content, False
        except google_api_exceptions.ResourceExhausted as e:
            print(f"Attempt {attempt + 1}: Rate limit exceeded for text: '{text_content[:50]}...'")
            if attempt < max_retries - 1:
                wait_time = initial_wait_time * (2 ** attempt)
                print(f"  Waiting {wait_time} seconds due to rate limit before retrying...")
                time.sleep(wait_time)
            else:
                print("Max retries reached due to persistent rate limits. Skipping translation for this segment.")
                return text_content, False
        except Exception as e:
            print(f"Attempt {attempt + 1}: General API error: {e} for text: '{text_content[:50]}...'")
            if attempt < max_retries - 1:
                wait_time = initial_wait_time * (2 ** attempt)
                print(f"  Waiting {wait_time} seconds due to error before retrying...")
                time.sleep(wait_time)
            else:
                print(f"Max retries reached due to persistent API errors. Skipping translation for this segment.")
                return text_content, False
    return text_content, False

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

def translate_html_file(file_path, model, base_prompt, translation_status_dict):
    """
    Reads an HTML file, translates its text content, and writes the modified content back.
    Updates the translation_status_dict based on success/failure within the file.
    """
    file_had_errors = False
    try:
        # Read file in binary mode to preserve encoding and potential BOM
        with open(file_path, 'rb') as f:
            content_bytes = f.read()

        # Determine parser based on lxml availability. No specific .xhtml vs .html handling.
        parser_name = 'html.parser' # Default fallback parser
        try:
            import lxml # Try to import lxml
            parser_name = 'lxml' # Use lxml for general HTML parsing
        except ImportError:
            pass # lxml not installed, stick to html.parser

        try:
            soup = BeautifulSoup(content_bytes, parser_name)
        except Exception as e:
            # If the chosen parser fails, try html.parser as a last resort
            print(f"Error parsing {os.path.basename(file_path)} with '{parser_name}': {e}. Attempting with 'html.parser'.")
            try:
                soup = BeautifulSoup(content_bytes, 'html.parser')
            except Exception as inner_e:
                print(f"Critical: Failed to parse {os.path.basename(file_path)} even with 'html.parser': {inner_e}. Skipping file.")
                translation_status_dict[file_path] = "failed"
                return False


        for text_node in soup.find_all(string=True):
            # Exclude script, style, title, meta, link, head, noscript, code tags
            if text_node.parent.name not in ['script', 'style', 'title', 'meta', 'link', 'head', 'noscript', 'code']:
                original_text = str(text_node).strip()
                
                # No advanced content filtering (e.g., for XML declarations, numbers) here
                # All text will be sent to API, relying on model to handle it based on prompt
                if original_text: # Ensure it's not empty after stripping
                    translated_text, success = translate_text(original_text, model, base_prompt)
                    if not success:
                        file_had_errors = True
                    if translated_text:
                        text_node.replace_with(translated_text)

        # Write file in binary mode with explicit UTF-8 encoding
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
        "--api_key",
        help="Your Google Gemini API Key. Will be used if provided, otherwise GOOGLE_API_KEY environment variable is checked."
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

    # Determine the API Key: prioritize argument, then environment variable
    api_key_to_use = args.api_key
    if not api_key_to_use:
        api_key_to_use = os.getenv("GOOGLE_API_KEY")
        if api_key_to_use:
            print("Using API Key from GOOGLE_API_KEY environment variable.")
        else:
            print("Error: No API Key provided. Please use --api_key or set GOOGLE_API_KEY environment variable.")
            return

    # Determine the translation prompt
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

    # Validate EPUB file path
    epub_path = os.path.abspath(args.epub_file_path)
    if not os.path.exists(epub_path):
        print(f"Error: EPUB file not found at '{epub_path}'")
        return
    if not epub_path.lower().endswith(".epub"):
        print(f"Error: The provided file '{epub_path}' does not appear to be an EPUB file.")
        return

    # Setup API
    if not setup_gemini_api(api_key_to_use):
        return

    model = genai.GenerativeModel(MODEL_NAME)

    epub_filename = os.path.basename(epub_path)
    epub_name_without_ext = os.path.splitext(epub_filename)[0]

    # Determine temporary directory path
    if args.temp_dir:
        temp_dir = os.path.abspath(args.temp_dir)
        print(f"Using specified temporary directory: {temp_dir}")
    else:
        temp_dir = os.path.join(os.getcwd(), f'temp_epub_translation_{epub_name_without_ext}')
        print(f"Using default temporary directory: {temp_dir}")

    output_epub_filename = f"{epub_name_without_ext}_zh-Hans.epub"
    output_epub_path = os.path.join(os.path.abspath(args.output_dir), output_epub_filename)
    # Status file is now always inside the temp_dir
    status_file_path = os.path.join(temp_dir, f'{epub_name_without_ext}_translation_status.json')

    os.makedirs(os.path.abspath(args.output_dir), exist_ok=True) # Ensure output dir exists
    os.makedirs(temp_dir, exist_ok=True) # Ensure temp_dir exists

    translation_status = {}
    if os.path.exists(status_file_path):
        try:
            with open(status_file_path, 'r', encoding='utf-8') as f:
                translation_status = json.load(f)
            print(f"Loaded previous translation status from: {status_file_path}")
        except json.JSONDecodeError:
            print(f"Warning: Could not read translation status file '{status_file_path}'. Starting fresh for this EPUB.")
        except Exception as e:
            print(f"Warning: Error loading translation status: {e}. Starting fresh for this EPUB.")

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
            if translate_html_file(html_file_abs_path, model, translation_base_prompt, translation_status):
                reprocessed_files_count += 1
            
            with open(status_file_path, 'w', encoding='utf-8') as f:
                json.dump(translation_status, f, indent=4)

        print(f"\nProcessed {reprocessed_files_count} files, skipped {skipped_files_count} already completed files.")

        if create_translated_epub(temp_dir, output_epub_path):
            print(f"\nTranslation complete! Translated EPUB saved to: {output_epub_path}")
        else:
            print("\nFailed to create the translated EPUB.")

    finally:
        all_completed = all(status == "completed" for status in translation_status.values())
        if all_completed and os.path.exists(temp_dir) and os.path.exists(status_file_path):
            cleanup_temp_dir(temp_dir) # This removes the temp_dir AND its contents, including the status file.
            print(f"Cleaned up temporary directory: {temp_dir}")
        else:
            print(f"\nTemporary directory '{temp_dir}' and status file '{status_file_path}' preserved for incremental translation (some files may still be 'failed' or 'pending').")

        print("\n--- Translation Process Finished ---")

# --- Run the script ---
if __name__ == "__main__":
    main()