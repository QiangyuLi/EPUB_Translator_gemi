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
from pathlib import Path

# --- Configuration ---

# Prioritize the most current and powerful models for general use.
MODELS = [
    {"name": "models/gemini-2.5-flash"},
    {"name": "models/gemini-2.5-pro"},
    {"name": "models/gemini-1.5-flash-latest"},
    {"name": "models/gemini-1.5-pro-latest"}
]

# Refined default prompt for clarity and strict adherence to rules.
DEFAULT_TRANSLATION_PROMPT = """
You are an expert translator. Your task is to translate the following content into **Simplified Chinese**.

**STRICT RULES:**
1. Translate the text **only if** it is meaningful, natural language content (sentences, paragraphs, phrases, or conversational text).
2. **DO NOT** translate or modify the input if it contains: structured content (XML, HTML, JSON), programming code, configuration, file paths, variable names, or consists only of symbols (e.g., `---`, `*`), isolated numbers, acronyms, or Roman numerals without context.
3. If translation is not applicable based on the rules, return the input text **EXACTLY AS RECEIVED** with **no modifications**, **no formatting**, and **no added or invented content**.
4. Do not include any introductory text, explanations, or labels. Output ONLY the translated text, or the original text unchanged if translation is not applicable.
"""

class GeminiEPUBTranslator:
    """
    Handles EPUB extraction, HTML parsing, and robust, incremental translation
    using the Google Gemini API with key/model cycling and caching.
    """
    def __init__(self, api_keys, models, base_prompt):
        if not api_keys:
            raise ValueError("API keys list cannot be empty.")
        if not models:
            raise ValueError("Models list cannot be empty.")

        # Cyclical iterators for API keys and models
        self.api_key_iterator = itertools.cycle(api_keys)
        self.model_iterator = itertools.cycle(models)
        self.api_keys = api_keys
        self.models = models
        
        # Current active configuration
        self.client = None
        self.model_name = None
        self.base_prompt = base_prompt
        self.max_retries_per_combination = 3
        self.initial_wait_time_on_error = 2 # seconds
        self.wait_time_on_all_combinations_exhausted = 60 # seconds

    def _setup_gemini_api(self, api_key, model_config):
        """Sets up the Google Gemini API with the provided key and model name."""
        model_name = model_config["name"]
        try:
            genai.configure(api_key=api_key)
            self.client = genai.GenerativeModel(model_name)
            self.model_name = model_name
            print(f"Gemini API configured: Key: {api_key[:5]}... | Model: {model_name}")
            return True
        except Exception as e:
            print(f"Error configuring API with key {api_key[:5]}... and model {model_name}: {e}")
            return False

    def _cycle_to_next_config(self):
        """
        Cycles to the next API key and model combination, and sets up the client.
        Tries all combinations before failing.
        Returns True on success, False if all combinations failed setup.
        """
        # We try up to the total number of combinations to ensure we check every possibility.
        for _ in range(len(self.api_keys) * len(self.models)):
            next_key = next(self.api_key_iterator)
            next_model_config = next(self.model_iterator)

            if self._setup_gemini_api(next_key, next_model_config):
                return True
        
        # If we reached here, it means all key-model combinations failed.
        return False
    
    def _is_meaningful_text(self, text):
        """
        Checks if a string is likely meaningful natural language by looking
        for a ratio of common language characters (letters, CJK, Cyrillic)
        and filtering out repeating symbols or pure numbers.
        """
        stripped_text = text.strip()
        if not stripped_text:
            return False
        
        # Check for pure number/symbol lines
        if re.fullmatch(r'[\d\s\.\,\-\+]+', stripped_text):
            return False
        
        # Define characters considered "meaningful" for translation
        # Includes: Latin, CJK (Chinese/Japanese/Korean), Cyrillic
        meaningful_chars = re.findall(r'[A-Za-z\u4e00-\u9fff\u0400-\u04ff]', text)
        
        # If less than 15% of the characters are meaningful, it's likely not worth translating
        if len(text) > 5 and len(meaningful_chars) / len(text) < 0.15:
            return False
            
        # Filter repetitive symbols that might contain a single letter (e.g., "----A----")
        if re.fullmatch(r'([-\*=/_#\.])+\s*[A-Za-z\u4e00-\u9fff\u0400-\u04ff]?\s*([-\*=/_#\.])+', stripped_text):
            return False
            
        return True

    def _translate_segment_with_retry(self, text_content):
        """
        Attempts translation, handling rate limits and general errors by
        retrying with the current config, then cycling to the next config,
        and finally pausing if all configurations are exhausted.
        Returns (translated_text, True) on success, (original_text, False) on persistent failure.
        """
        if not text_content.strip():
            return "", True

        if not self._is_meaningful_text(text_content):
            print(f"  Skipping non-meaningful text (pre-filter): {text_content[:70]}{'...' if len(text_content) > 70 else ''}")
            return text_content, True

        prompt = f"{self.base_prompt}\n\n{text_content}"
        
        # Total combinations to try before a long wait
        max_combinations = len(self.api_keys) * len(self.models)
        
        # Outer loop to handle key/model cycling
        for combination_attempt in range(max_combinations):
            if self.client is None:
                if not self._cycle_to_next_config():
                    print("Critical: All initial API key/model combinations failed to set up.")
                    return text_content, False

            # Inner loop for retries within the current combination
            for attempt in range(self.max_retries_per_combination):
                try:
                    response = self.client.generate_content(prompt)
                    
                    if response and response.text:
                        translated_text = response.text.strip()
                        print(f"  Original: {text_content[:70]}{'...' if len(text_content) > 70 else ''}")
                        print(f"  Translated: {translated_text[:70]}{'...' if len(translated_text) > 70 else ''}\n")
                        return translated_text, True
                    else:
                        raise RuntimeError("Empty or invalid API response.")

                except google_api_exceptions.ResourceExhausted:
                    print(f"Attempt {attempt + 1}: Rate limit exceeded for {self.model_name}. Cycling to next key/model...")
                    break # Break inner loop, forces combination_attempt increment

                except Exception as e:
                    print(f"Attempt {attempt + 1}: General API error ({self.model_name}): {e}. Retrying...")
                    if attempt < self.max_retries_per_combination - 1:
                        wait_time = self.initial_wait_time_on_error * (2 ** attempt)
                        time.sleep(wait_time)
                    else:
                        print("  Max retries reached with current combination due to errors. Cycling to next key/model...")
                        break # Break inner loop, forces combination_attempt increment
            
            # If the inner loop broke (rate limit or max retries), try to cycle
            if combination_attempt < max_combinations - 1:
                # Cycle to the next combination for the next attempt
                self._cycle_to_next_config()
                continue
        
        # If all combinations have been tried (max_combinations reached), wait and restart
        print(f"All API key/model combinations exhausted or rate-limited. Waiting {self.wait_time_on_all_combinations_exhausted} seconds before full retry.")
        time.sleep(self.wait_time_on_all_combinations_exhausted)
        # Recursive call after waiting. In a real long-running script, this could be risky,
        # but for this specific failure mode (all rate-limited), it's the intended recovery.
        # Alternatively, a simple False return here could be safer for critical scripts.
        return self._translate_segment_with_retry(text_content)


    def _extract_epub(self, epub_path, extract_to_dir):
        """Extracts the contents of an EPUB file."""
        try:
            with zipfile.ZipFile(epub_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to_dir)
            print(f"EPUB extracted to: {extract_to_dir}")
            return True
        except Exception as e:
            print(f"Error extracting EPUB: {e}")
            return False

    def _find_html_files(self, directory):
        """Finds all HTML/XHTML files in the extracted EPUB directory."""
        return list(directory.glob('**/*.*html'))

    def _translate_html_file(self, file_path, temp_dir, translation_status_dict, translation_cache):
        """
        Reads an HTML file, translates its text content, and writes the modified content back.
        """
        file_had_errors = False
        file_relative_path = file_path.relative_to(temp_dir).as_posix()

        if file_relative_path not in translation_cache:
            translation_cache[file_relative_path] = {}

        try:
            # Read the file content bytes
            content_bytes = file_path.read_bytes()

            # Determine the best parser
            try:
                import lxml
                parser_name = 'lxml'
            except ImportError:
                parser_name = 'html.parser'

            try:
                soup = BeautifulSoup(content_bytes, parser_name)
            except Exception as e:
                print(f"Error parsing {file_path.name}: {e}. Skipping file.")
                translation_status_dict[file_relative_path] = "failed"
                return False

            for text_node in soup.find_all(string=True):
                # Skip text inside script, style, meta, etc. tags
                if text_node.parent.name not in ['script', 'style', 'title', 'meta', 'link', 'head', 'noscript', 'code']:
                    original_text = str(text_node).strip()
                    
                    if original_text:
                        # Use hash for cache lookup
                        text_hash = hashlib.sha256(original_text.encode('utf-8')).hexdigest()
                        
                        translated_text = None
                        if text_hash in translation_cache[file_relative_path]:
                            # 1. Use cache
                            translated_text = translation_cache[file_relative_path][text_hash]
                            print(f"  Reusing cached translation for: {original_text[:70]}{'...' if len(original_text) > 70 else ''}")
                            print(f"  Cached: {translated_text[:70]}{'...' if len(translated_text) > 70 else ''}\n")
                        else:
                            # 2. Translate with API
                            translated_text, success = self._translate_segment_with_retry(original_text)
                            
                            if not success:
                                file_had_errors = True
                            
                            if translated_text:
                                # 3. Update cache
                                translation_cache[file_relative_path][text_hash] = translated_text

                        if translated_text:
                            # Replace the text node with the translated content
                            text_node.replace_with(translated_text)

            # Write the modified soup back to the file
            file_path.write_bytes(soup.encode('utf-8'))

            if file_had_errors:
                translation_status_dict[file_relative_path] = "failed"
                print(f"Finished processing: {file_path.name} (Some segments failed)\n")
            else:
                translation_status_dict[file_relative_path] = "completed"
                print(f"Finished processing: {file_path.name} (All segments successful)\n")
            return True
        except Exception as e:
            print(f"Critical error processing HTML file {file_path.name}: {e}")
            translation_status_dict[file_relative_path] = "failed"
            return False

    def _create_translated_epub(self, source_dir, output_epub_path):
        """Creates a new EPUB file from the modified contents."""
        try:
            mimetype_path = source_dir / 'mimetype'
            if not mimetype_path.exists():
                print("Error: mimetype file not found. Cannot create EPUB.")
                return False

            with zipfile.ZipFile(output_epub_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Mimetype must be uncompressed and first in the ZIP archive
                zf.write(mimetype_path, 'mimetype', compress_type=zipfile.ZIP_STORED)

                # Recursively write all other files
                for item in source_dir.rglob('*'):
                    if item.is_file() and item.name != 'mimetype':
                        arcname = item.relative_to(source_dir).as_posix()
                        zf.write(item, arcname)
            
            print(f"Translated EPUB created at: {output_epub_path}")
            return True
        except Exception as e:
            print(f"Error creating translated EPUB: {e}")
            return False

    def _cleanup_temp_dir(self, temp_dir):
        """Removes the temporary directory."""
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            print(f"Cleaned up temporary directory: {temp_dir}")

    def translate_epub(self, epub_path, output_dir, temp_dir_path, prompt_file=None):
        """The main orchestration method for the translation process."""
        
        # --- File Path Setup ---
        epub_path = Path(epub_path).resolve()
        output_dir = Path(output_dir).resolve()
        
        epub_filename = epub_path.name
        epub_name_without_ext = epub_path.stem

        if temp_dir_path:
            temp_dir = Path(temp_dir_path).resolve()
        else:
            temp_dir = Path.cwd() / f'temp_epub_translation_{epub_name_without_ext}'

        output_epub_filename = f"{epub_name_without_ext}_zh-Hans.epub"
        output_epub_path = output_dir / output_epub_filename
        
        output_dir.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

        status_file_path = temp_dir / f'{epub_name_without_ext}_file_status.json'
        cache_file_path = temp_dir / f'{epub_name_without_ext}_translation_cache.json'

        # --- Load Prompt ---
        translation_base_prompt = self.base_prompt
        if prompt_file:
            try:
                custom_prompt_content = Path(prompt_file).read_text(encoding='utf-8').strip()
                if custom_prompt_content:
                    translation_base_prompt = custom_prompt_content + "\n\n"
                    print(f"Using custom prompt from: {prompt_file}")
            except Exception as e:
                print(f"Warning: Could not read prompt file '{prompt_file}': {e}. Using default prompt.")

        self.base_prompt = translation_base_prompt
        
        # --- Load State (Status and Cache) ---
        translation_status = {}
        translation_cache = {}
        
        try:
            if status_file_path.exists():
                translation_status = json.loads(status_file_path.read_text(encoding='utf-8'))
                print(f"Loaded previous file-level translation status from: {status_file_path}")
            if cache_file_path.exists():
                translation_cache = json.loads(cache_file_path.read_text(encoding='utf-8'))
                print(f"Loaded previous sentence-level translation cache from: {cache_file_path}")
        except json.JSONDecodeError:
            print("Warning: Failed to decode status/cache JSON. Starting fresh for this EPUB.")
        except Exception as e:
            print(f"Warning: Error loading state files: {e}. Starting fresh.")

        print(f"\n--- Starting EPUB Translation for '{epub_filename}' ---")
        print(f"Temporary directory: {temp_dir}")
        print(f"Output EPUB will be saved to: {output_epub_path}")

        # --- Extraction ---
        if not (temp_dir / 'mimetype').exists():
             print(f"Temporary directory '{temp_dir.name}' is empty. Extracting EPUB.")
             if not self._extract_epub(epub_path, temp_dir):
                 self._cleanup_temp_dir(temp_dir)
                 return
        else:
            print(f"Temporary directory '{temp_dir.name}' already contains files. Re-using for incremental translation.")

        # --- Translation Loop ---
        try:
            html_files = self._find_html_files(temp_dir)
            if not html_files:
                print("No HTML/XHTML files found in the EPUB. Nothing to translate.")
                return

            print(f"Found {len(html_files)} HTML files in EPUB structure.")
            reprocessed_files_count = 0
            skipped_files_count = 0

            # Initial API setup attempt
            if self.client is None and not self._cycle_to_next_config():
                 print("Critical: Failed to set up any Gemini API key/model combination initially. Exiting.")
                 return

            for i, html_file_path in enumerate(html_files):
                html_file_rel_path = html_file_path.relative_to(temp_dir).as_posix()
                current_file_status = translation_status.get(html_file_rel_path, "pending")

                if current_file_status == "completed":
                    print(f"Skipping completed file {i+1}/{len(html_files)}: {html_file_path.name}")
                    skipped_files_count += 1
                    continue

                print(f"\n--- Translating file {i+1}/{len(html_files)}: {html_file_path.name} --- (Status: {current_file_status}, Model: {self.model_name})")
                
                if self._translate_html_file(html_file_path, temp_dir, translation_status, translation_cache):
                    reprocessed_files_count += 1
                
                # Save status and cache after every file processed
                status_file_path.write_text(json.dumps(translation_status, indent=4, ensure_ascii=False), encoding='utf-8')
                cache_file_path.write_text(json.dumps(translation_cache, indent=4, ensure_ascii=False), encoding='utf-8')

            print(f"\nProcessed {reprocessed_files_count} files, skipped {skipped_files_count} already completed files.")

            # --- Final EPUB Creation ---
            if self._create_translated_epub(temp_dir, output_epub_path):
                print(f"\nTranslation complete! Translated EPUB saved to: {output_epub_path}")
            else:
                print("\nFailed to create the translated EPUB.")

        finally:
            all_completed = all(status == "completed" for status in translation_status.values())
            if all_completed and status_file_path.exists() and cache_file_path.exists():
                self._cleanup_temp_dir(temp_dir)
                print(f"Cleaned up temporary directory: {temp_dir}")
            else:
                print(f"\nTemporary directory '{temp_dir.name}', status, and cache preserved for incremental translation (some files may still be 'failed' or 'pending').")

            print("\n--- Translation Process Finished ---")

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

    # --- API Key Acquisition ---
    api_keys = []
    if args.api_keys:
        api_keys = args.api_keys
        print(f"Using {len(api_keys)} API Key(s) from command line arguments.")
    else:
        env_api_key = os.getenv("GOOGLE_API_KEY")
        if env_api_key:
            api_keys = [env_api_key]
            print("Using API Key from GOOGLE_API_KEY environment variable.")
        else:
            print("Error: No API Key(s) provided. Please use --api_keys KEY1 KEY2... or set GOOGLE_API_KEY environment variable.")
            return

    if not api_keys:
        print("Error: No valid API keys found. Exiting.")
        return

    try:
        translator = GeminiEPUBTranslator(
            api_keys=api_keys, 
            models=MODELS, 
            base_prompt=DEFAULT_TRANSLATION_PROMPT
        )
        translator.translate_epub(
            epub_path=args.epub_file_path,
            output_dir=args.output_dir,
            temp_dir_path=args.temp_dir,
            prompt_file=args.prompt_file
        )
    except ValueError as e:
        print(f"Configuration Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during the main process: {e}")


if __name__ == "__main__":
    main()
