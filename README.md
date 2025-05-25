# EPUB Translator powered by Google Gemini

This Python script allows you to translate EPUB e-book files into **Simplified Chinese** using the **Google Gemini API**. It's designed for command-line use, offering features like custom prompts, incremental translation (to resume if interrupted), and robust error handling with retries for API calls.

---

## Features

* **EPUB Translation:** Translates the text content of EPUB files to Simplified Chinese.
* **Google Gemini API:** Utilizes the `gemini-2.0-flash-lite` model for translation, chosen for its cost-effectiveness and speed.
* **Command-Line Interface:** Easy to use from your terminal with arguments for input file, API key, and output directory.
* **Customizable Prompt:** Use a built-in default translation prompt or provide your own detailed instructions from a text file to guide the Gemini model's translation style.
* **Incremental Translation & Resume:**
    * If a translation process is interrupted (e.g., API errors, network issues, script termination), you can **restart the script with the same command**.
    * It will automatically detect previously processed HTML files and only re-translate files that were **unsuccessful** or **not yet processed**, saving time and API quota.
* **Robust Error Handling:** Includes exponential backoff and retries for API errors (like rate limits) to maximize translation success. Individual sentence translation failures are skipped, allowing the rest of the book to process.
* **Temporary File Management:** Extracts EPUB contents to a temporary directory and cleans up upon full completion.

---

## Prerequisites

Before you begin, make sure you have the following:

1.  **Python 3.7+:** Installed on your system.
2.  **Google Gemini API Key:** You can obtain one from [Google AI Studio](https://aistudio.google.com/app/apikey).
3.  **Required Python Libraries:** Install them using pip:
    ```bash
    pip install beautifulsoup4 google-generativeai
    ```

---

## How to Use

1.  **Save the Script:**
    Save the provided Python code into a file, for example, `translate_epub.py`.

2.  **Prepare Your EPUB File:**
    Ensure your EPUB file is accessible on your system.

3.  **Prepare Your Custom Prompt (Optional):**
    If you want to use a custom translation prompt, create a plain text file (e.g., `my_prompt.txt`) and write your instructions in it. For example:
    ```text
    Translate the following English text into highly formal and literary Simplified Chinese, maintaining the original tone and context as much as possible. Do not translate proper nouns unless explicitly specified.
    ```
    The content of this file will be prepended to each text segment sent to the Gemini API.

4.  **Run from Command Line:**

    Open your terminal or command prompt and navigate to the directory where you saved `translate_epub.py`.

    * **Using API Key from Command-Line Argument (Preferred):**
        ```bash
        python translate_epub.py /path/to/your/book.epub --api_key YOUR_GEMINI_API_KEY
        ```
        Replace `/path/to/your/book.epub` with the actual path to your EPUB file and `YOUR_GEMINI_API_KEY` with your Gemini API key.

    * **Using API Key from Environment Variable (Fallback):**
        If you don't provide `--api_key`, the script will look for an environment variable named `GOOGLE_API_KEY`.
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
        * **Windows (PowerShell):**
            ```powershell
            $env:GOOGLE_API_KEY="YOUR_GEMINI_API_KEY"
            python translate_epub.py C:\path\to\your\book.epub
            ```
        The script prioritizes the command-line argument if both are present.

    * **Specifying Output Directory:**
        ```bash
        python translate_epub.py my_book.epub --api_key YOUR_GEMINI_API_KEY --output_dir /home/user/translated_epubs
        ```

    * **Using a Custom Prompt File:**
        ```bash
        python translate_epub.py my_book.epub --api_key YOUR_GEMINI_API_KEY --prompt_file my_prompt.txt
        ```

### Understanding the Output

As the script runs, you'll see progress messages in your terminal:
* Confirmation of API configuration and model used.
* Messages about extracting the EPUB.
* For each translated text segment, you'll see a line with "Original:" and "Translated:".
* Progress updates for each HTML file within the EPUB.
* Messages about rate limits or other API errors, indicating retries or skips.

---

## Resuming Interrupted Translations

If the script stops due to an error, a network issue, or if you manually stop it:

1.  **Simply run the exact same command again.**
2.  The script will detect the temporary files and a status file (`[epub_name]_translation_status.json`) from the previous run.
3.  It will intelligently **resume** by skipping HTML files that were already successfully translated and focusing only on those that were marked "failed" or were not processed yet.
4.  Once all parts of the EPUB are successfully translated, the temporary files and the status file will be automatically cleaned up. If some parts remain "failed" due to persistent issues, the temporary directory will be preserved for future attempts.

---

## Important Considerations

* **API Key Security:** Always keep your API key secure. Avoid hardcoding it directly in the script.
* **API Quota:** Google Gemini API usage is subject to quotas. If you encounter "quota exceeded" errors, you may need to check your [Google Cloud Console's Quotas and Billing](https://console.cloud.google.com/iam-admin/quotas) to review your limits or request an increase.
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

# EPUB 翻译器更新说明

## 中文 (Chinese)

### 版本更新 - 提升稳定性和用户体验

此版本对 EPUB 翻译器进行了多项关键改进，旨在提高翻译的准确性、过程的稳定性以及用户体验。

#### 主要改进:

1.  **API 密钥循环与智能等待 (API Key Cycling with Smart Waiting):**
    * **多密钥支持:** 现在您可以提供多个 Gemini API 密钥。脚本将自动在这些密钥之间循环，以应对速率限制。当一个密钥达到限制时，它将尝试切换到下一个可用密钥。
    * **自动等待机制:** 如果所有提供的 API 密钥都达到了速率限制，脚本将不再立即跳过翻译，而是进入等待模式（默认等待 60 秒），然后重新尝试轮换密钥并继续翻译。这大大减少了因 API 限制而导致翻译中断的情况。
    * **更高鲁棒性:** 结合了指数退避重试、密钥轮换和智能等待，确保了在网络波动或 API 负载高时翻译过程的持续性。

2.  **句子级翻译进度保存与续传 (Sentence-Level Progress Saving and Resumption):**
    * **缓存机制:** 脚本现在会创建一个名为 `_translation_cache.json` 的临时文件，用于保存每个已翻译文本段落的原文和译文。
    * **断点续传:** 在后续运行中，如果遇到已在缓存中的文本，脚本将直接使用缓存的译文，而不再调用 API。这不仅节省了 API 配额，也使得翻译大型 EPUB 文件时可以中断并随时恢复，无需从头开始。
    * **效率提升:** 显著减少了重复翻译，加快了对已部分翻译书籍的处理速度。

3.  **精确的非自然语言过滤 (Precise Non-Natural Language Filtering):**
    * **智能识别:** 增强了 `is_meaningful_text` 函数，可以更准确地识别并跳过那些不应该被翻译的文本，例如纯符号行（如 `-----------`）、结构化数据、代码片段、纯数字或只有少量字母的重复符号模式。
    * **避免误译:** 这解决了之前版本中将 `-----------` 这类分隔符错误翻译成有意义短语的问题，确保了翻译结果的纯净性。

4.  **临时文件管理优化 (Optimized Temporary File Management):**
    * 临时工作目录及其中的状态和缓存文件，只有在整个 EPUB 翻译完全成功后才会被自动清理。如果在翻译过程中有任何文件失败或中止，临时目录将被保留，以便用户检查问题并进行增量翻译。

## English

### Version Updates - Enhancing Stability and User Experience

This version introduces several key improvements to the EPUB translator, aiming to enhance translation accuracy, process stability, and overall user experience.

#### Key Improvements:

1.  **API Key Cycling with Smart Waiting:**
    * **Multi-Key Support:** You can now provide multiple Gemini API keys. The script will automatically cycle through these keys to handle rate limits. When one key is rate-limited, it will attempt to switch to the next available key.
    * **Automatic Waiting Mechanism:** If all provided API keys become rate-limited, the script will no longer skip translation immediately. Instead, it will enter a waiting mode (defaulting to 60 seconds) before attempting to cycle keys and resume translation. This significantly reduces interruptions due to API constraints.
    * **Increased Robustness:** The combination of exponential backoff, key rotation, and smart waiting ensures continuous translation even during network fluctuations or high API load.

2.  **Sentence-Level Progress Saving and Resumption:**
    * **Caching Mechanism:** The script now creates a temporary file named `_translation_cache.json` to save the original and translated text for each processed segment.
    * **Resumable Progress:** In subsequent runs, if the script encounters text already present in the cache, it will reuse the cached translation instead of making a new API call. This saves API quota and allows for pausing and resuming translation of large EPUB files without starting from scratch.
    * **Efficiency Boost:** Significantly reduces redundant translations and speeds up processing for partially translated books.

3.  **Precise Non-Natural Language Filtering:**
    * **Intelligent Recognition:** The `is_meaningful_text` function has been enhanced to more accurately identify and skip text that should not be translated, such as lines consisting purely of symbols (e.g., `-----------`), structured data, code snippets, pure numbers, or repetitive symbol patterns with minimal alphanumeric content.
    * **Prevents Mistranslations:** This addresses previous issues where delimiters like `-----------` were incorrectly translated into meaningful phrases, ensuring cleaner translation output.

4.  **Optimized Temporary File Management:**
    * The temporary working directory, including its status and cache files, will now only be automatically cleaned up after the entire EPUB translation process is fully successful. If any files fail or the process is aborted, the temporary directory will be preserved, allowing users to inspect issues and perform incremental translations.