# EPUB Translator powered by Google Gemini

This Python script allows you to translate EPUB e-book files into **Simplified Chinese** using the **Google Gemini API**. It's designed for command-line use, offering features like custom prompts, incremental translation, and robust error handling with **API key cycling** for maximum resilience against rate limits.

---

## Features

* **EPUB Translation:** Translates the text content of EPUB files to Simplified Chinese.
* **Google Gemini API:** Utilizes the **latest Gemini models** (prioritizing `gemini-2.5-flash` and `gemini-1.5-latest`) for translation, chosen for their balance of quality, speed, and cost-effectiveness.
* **Command-Line Interface:** Easy to use from your terminal with arguments for the input file, API keys, and output directory.
* **Customizable Prompt:** Use a built-in default translation prompt or provide your own detailed instructions from a text file to guide the Gemini model's translation style.
* **Incremental Translation & Resume:**
    * **File-Level Resume:** Automatically detects previously processed HTML files, skipping successful ones.
    * **Sentence-Level Caching:** Uses a cache file (`_translation_cache.json`) to store and reuse translations of individual text segments, saving API quota and enabling true, efficient resumption from where it left off.
* **Robust Error Handling & Resilience:**
    * **Multi-Key Cycling:** Supports providing **multiple API keys** and automatically cycles between them to handle rate limits and service failures.
    * **Smart Waiting:** Implements exponential backoff and a **smart waiting period** if all provided keys are simultaneously rate-limited, maximizing the chance of eventual success without manual intervention.
* **Precise Content Filtering:** Intelligent recognition and skipping of non-natural language content (e.g., code snippets, pure symbols, metadata, or pure numbers) to ensure cleaner translation output.
* **Temporary File Management:** Extracts EPUB contents to a temporary directory and preserves this directory only if the translation is incomplete or failed, allowing for easy resumption.

---

## Prerequisites

Before you begin, make sure you have the following:

1.  **Python 3.7+:** Installed on your system.
2.  **Google Gemini API Key(s):** You can obtain one or more from [Google AI Studio](https://aistudio.google.com/app/apikey).
3.  **Required Python Libraries:** Install them using pip:
    ```bash
    pip install beautifulsoup4 google-generativeai lxml
    ```
    *(Note: The script attempts to use the faster `lxml` parser if available, otherwise it falls back to `html.parser`.)*

---

## How to Use

1.  **Save the Script:**
    Save the provided Python code into a file, for example, `translate_epub.py`.

2.  **Prepare Your EPUB File:**
    Ensure your EPUB file is accessible on your system.

3.  **Prepare Your Custom Prompt (Optional):**
    If you want to use a custom translation prompt, create a plain text file (e.g., `my_prompt.txt`) and write your instructions in it. The content of this file will be prepended to each text segment sent to the Gemini API.

4.  **Run from Command Line:**

    Open your terminal or command prompt and navigate to the directory where you saved `translate_epub.py`.

    * **Using API Keys from Command-Line Argument (Preferred):**
        Use the **`--api_keys`** flag followed by one or more keys, separated by spaces.
        ```bash
        python translate_epub.py /path/to/your/book.epub --api_keys KEY1 KEY2 KEY3
        ```
        Replace `/path/to/your/book.epub` with the actual path to your EPUB file and `KEY1 KEY2 KEY3` with your Gemini API keys. Using multiple keys is highly recommended for large files.

    * **Using API Key from Environment Variable (Fallback):**
        If you don't provide `--api_keys`, the script will look for an environment variable named **`GOOGLE_API_KEY`**.
        * **Linux/macOS:**
          ```bash
          export GOOGLE_API_KEY="YOUR_GEMINI_API_KEY"
          python translate_epub.py /path/to/your/book.epub
          ```
        * **Windows (Command Prompt):**
          ```cmd
          set GOOGLE_API_KEY="YOUR_GEMINI_API_KEY"
          python translate_epub.py C:\path\to\your\book.epub
          ```
        The script will use the environment variable as a single key and cycle through available models.

    * **Specifying Output Directory:**
        ```bash
        python translate_epub.py my_book.epub --api_keys KEY1 --output_dir /home/user/translated_epubs
        ```

    * **Using a Custom Prompt File:**
        ```bash
        python translate_epub.py my_book.epub --api_keys KEY1 --prompt_file my_prompt.txt
        ```

### Understanding the Output

As the script runs, you'll see progress messages in your terminal:
* Confirmation of API configuration, including the **key prefix and model currently in use.**
* Messages indicating when the script is **reusing a cached translation** instead of calling the API.
* Messages about rate limits, confirming when the script is **cycling to the next API key** or entering the **smart waiting period.**
* Progress updates for each HTML file within the EPUB.

---

## Resuming Interrupted Translations

If the script stops due to an error, a network issue, or if you manually stop it:

1.  **Simply run the exact same command again.**
2.  The script will detect the temporary files, including the **sentence-level cache** (`_translation_cache.json`) and the **file status log**.
3.  It will intelligently **resume** by reusing cached translations and focusing only on files that were marked "failed" or were not processed yet.
4.  Once all parts of the EPUB are successfully translated, the temporary files and state files will be automatically cleaned up. If some parts remain "failed" due to persistent issues, the temporary directory will be preserved for future attempts.

---

## Important Considerations

* **API Key Security:** Always keep your API key secure. Use command-line arguments or environment variables rather than hardcoding.
* **API Quota:** Google Gemini API usage is subject to quotas. The **multi-key cycling** feature helps mitigate rate limits, but you should still monitor your overall quota in the [Google Cloud Console's Quotas and Billing](https://console.cloud.google.com/iam-admin/quotas).
* **Internet Connection:** A stable internet connection is essential for communication with the Gemini API.
* **EPUB Structure:** The script primarily focuses on translating text content found within HTML/XHTML files inside the EPUB. Complex layouts or non-standard EPUB structures might yield unexpected results.
* **Translation Quality:** The quality of the translation depends on the Gemini model and the effectiveness of your prompt. Experiment with custom prompts for better results.

---

## 免责声明 (Disclaimer)

本脚本仅用于个人学习和研究目的。开发者不对使用本脚本可能造成的任何数据丢失、内容不准确或违反任何平台服务条款的行为负责。

在使用 Google Gemini API 时，请务必遵守 Google 的[服务条款](https://policies.google.com/terms)和[生成式人工智能使用政策](https://developers.google.com/gemini/usage-policies)。您对通过本脚本使用 Google Gemini API 产生的任何费用和内容负全部责任。

本脚本与 Google 或任何其他公司**没有关联**，也**未获得其认可**。这是一个独立的工具。

在将翻译后的内容用于任何公开发布或商业用途之前，请务必进行人工审查和校对，以确保准确性和合规性。

---

## Disclaimer

This script is provided for personal learning and research purposes only. The developer is not responsible for any data loss, content inaccuracies, or violations of platform terms of service that may arise from the use of this script.

When using the Google Gemini API, you must comply with Google's [Terms of Service](https://policies.google.com/terms) and [Generative AI Usage Policy](https://developers.google.com/gemini/usage-policies). You are solely responsible for any costs and content generated through the use of the Google Gemini API via this script.

This script is **not affiliated with or endorsed by Google** or any other company. It is an independent tool.

Always perform a manual review and proofreading of the translated content to ensure accuracy and compliance before using it for any public distribution or commercial purposes.
