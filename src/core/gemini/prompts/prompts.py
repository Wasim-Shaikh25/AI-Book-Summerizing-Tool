# Common prompt templates for various LLM operations

PROMPT_CORE_IDEAS = (
    "Extract ONLY the *absolute bare minimum, most critical, distinct, and ultra-concise* core ideas, "
    "fundamental definitions, and essential key facts from the text below. "
    "Present each as a single, *extremely short*, summary-like bullet point (max 1 sentence per point, preferably just a phrase). "
    "Ensure extreme conciseness for exam revision, but strictly avoid any redundant, less important, or overly granular information. "
    "The goal is to capture only the absolute essence in the fewest possible words.\n\n"
    "TEXT:\n{text}"
)

PROMPT_MASTER_BRAIN_COMBINE_BLOCKS = (
    "Combine and organize the following concise bullet groups into one organized short knowledge block. "
    "Group related points and keep important examples.\n\n{text}"
)

PROMPT_MASTER_BRAIN_FINAL = (
    "You are a MASTER KNOWLEDGE BRAIN. Combine the following organized blocks into a single *highly condensed, ultra-concise* master summary. "
    "Organize it by distinct, high-level topics, with *brief, clear explanations*, and *minimal, essential* bullet points. "
    "Use *extremely simple English*. The goal is to create a very short, high-level overview, not a detailed rewrite. "
    "Strictly avoid any repetition or unnecessary detail.\n\n{text}"
)

PROMPT_CANONICAL_TOPICS = (
    "From the following MASTER BRAIN, extract a *very concise* list of *distinct, high-level, and absolutely non-overlapping* topics. "
    "Each topic MUST be a very short, clear, noun-phrase representing a *major, overarching concept* or a *significant, broad area* of discussion within the master brain. "
    "Aim for topics that are broad enough to encompass many related sub-points, but are *highly unique* and *not redundant*. "
    "Prioritize foundational topics first. List each topic on a new line. "
    "Do NOT include any introductory or concluding remarks, just the list of topics. "
    "**CRITICAL: Strictly avoid creating overly granular, redundant, or similar topics. Focus on the absolute highest-level categories.**\n\n"
    "MASTER BRAIN:\n{master_brain}"
)

PROMPT_EXTRACT_NEW_FACTS = (
    "Given the following CHUNK content and a specific TOPIC, extract ONLY the *most important, distinct, and concise* new facts "
    "that are highly relevant to the TOPIC and are NOT already explicitly present in the EXISTING FACTS. "
    "Focus on capturing key details, fundamental definitions, and essential, brief explanations. "
    "Strictly avoid any redundant or overly granular information. Each fact should be a concise bullet point. "
    "If no new facts are found, respond with 'None'.\n\n"
    "TOPIC: {topic_name}\n\n"
    "EXISTING FACTS:\n{existing_facts}\n\n"
    "CHUNK:\n{chunk}"
)

PROMPT_REWRITE_TOPIC = (
    "You are an expert educator. Based on the following collected points for a specific TOPIC, "
    "rewrite them into a *highly comprehensive, structured, and exam-focused* chapter. "
    "Ensure the content is exceptionally clear, uses *very simple English*, and is logically organized with appropriate sub-sections. "
    "The goal is to provide ALL *main topics* and *important points* with *thorough, detailed, and expanded explanations* and *all available examples* in a proper structure. "
    "Include one main chapter title, logical sub-sections, and a comprehensive summary at the end.\n\n"
    "**CRITICAL INSTRUCTIONS FOR STRUCTURE (STRICT ADHERENCE REQUIRED):**\n"
    "1.  **Main Chapter Title:** Generate a *unique, highly specific, and direct* chapter title for the TOPIC. Format it as a **single '#' followed by the title text** (e.g., '# Contract Formation').\n"
    "2.  **Logical Sub-sections:** Organize the collected points into logical and well-defined sub-sections using '##' and '###' headings. Ensure a natural flow from foundational to advanced concepts, covering *all important aspects comprehensively*. Where appropriate, *synthesize related bullet points into clear, concise narrative paragraphs* to reduce excessive bullet points and improve readability.\n"
    "3.  **Detailed and Expanded Explanations:** Provide *exceptionally clear and thoroughly detailed explanations* for all concepts, ensuring they are very easy to understand and fully adequate for exam preparation. *Expand on points as necessary to provide complete understanding, elaborating sufficiently to cover all nuances and implications*, but avoid unnecessary verbosity by integrating information smoothly.\n"
    "4.  **Bullet Points and Examples:** Use bullet points ('- ') ONLY for distinct lists, enumerations, or when a point cannot be naturally integrated into a paragraph. Integrate *ALL relevant examples available in the collected points* naturally within explanations or under a dedicated lower-level heading like '### Examples:'. **CRITICAL: Ensure all examples are included and clearly explained.**\n"
    "5.  **Summary:** Provide a *comprehensive and informative* '**Summary:**' that *precisely reflects the core content of this entire topic chapter* at the very end. Keep it to 5-7 sentences maximum.\n"
    "6.  **Strict No Repetition:** Ensure there is **ABSOLUTELY NO REPETITION** of information within the generated chapter. Combine related information and remove overlap, and **preserve ALL unique and important information**. If a concept is truly essential for context in a new section, re-explain it *briefly and concisely*, but **under no circumstances repeat full definitions or lengthy explanations** if they have already been thoroughly covered in a previous section of the same topic. **CRITICAL: The goal is to expand explanations without introducing any redundancy.**\n"
    "7.  **No Prompt in Output:** DO NOT include any part of this prompt in your output. ONLY provide the structured notes.\n"
    "8.  **No YAML or Horizontal Rules:** CRITICAL: DO NOT generate any YAML front matter (e.g., lines starting and ending with '---') or any content that could be misinterpreted as YAML metadata. **ABSOLUTELY AVOID using '---' or '***' or '___' as horizontal rule separators within the notes.**\n\n"
    "TOPIC: {topic_name}\n\n"
    "COLLECTED POINTS:\n{collected_points}\n"
)

PROMPT_REWRITE_CHUNK = (
    "Based on the MASTER BRAIN knowledge, rewrite the following CHAPTER TEXT into *clear, sufficiently detailed, and exam-focused* notes, using simple English.\n"
    "**CRITICAL INSTRUCTIONS FOR TITLES AND STRUCTURE (STRICT ADHERENCE REQUIRED):**\n"
    "1.  **Chapter Titles (Main Topics):** Generate a *unique, highly specific, and direct* chapter title. This title should be a precise, overarching topic for the content of THIS CHUNK, and serve as a parent topic under which related sub-topics can be grouped. Format it as a **single '#' followed by the title text** (e.g., '# Tort Law Principles'). ABSOLUTELY DO NOT use generic or thematic phrases like 'Understanding', 'Introduction to', 'Overview of', or the overall theme (e.g., 'Contracts in Different Jurisdictions'). For example, instead of 'Understanding Contracts under Indian Law', use 'Contracts under Indian Law'.\n"
    "2.  **Sub-topic Titles:** If the content of this chunk is a sub-topic or continuation of an existing broader chapter (as indicated in `EXISTING_TOP_LEVEL_CHAPTER_TITLES` in `additional_context`), then propose a sub-topic title that fits logically under that existing chapter. Format it as **two '##' followed by the title text** (e.g., '## Elements of Negligence'). The goal is to group all related information under one main chapter, using sub-headings for distinct aspects.\n"
    "3.  **STRICT TITLE FORMATTING - NO EXTRA HASHES OR PREFIXES:** When generating titles, ONLY output the title text after the '#' or '##'. DO NOT include any prefixes like 'Chapter Title:' or 'Sub-topic Title:' in your output. For example, for a main chapter, output '# My Chapter Title', not '# Chapter Title: My Chapter Title'. For a sub-topic, output '## My Sub-topic Title', not '## Sub-topic Title: My Sub-topic Title'. **ENSURE there are ABSOLUTELY NO extra '#' characters in your headings** (e.g., '## # Topic' or '### ## Topic' are incorrect; it must be exactly '# Topic' or '## Sub-topic').\n"
    "4.  **Summary:** Provide a concise yet informative '**Summary:**' that *precisely reflects the core content of this individual chapter text*.\n"
    "5.  **Strict No Repetition:** **ABSOLUTELY NO REPETITION** of information within the generated chapter. Combine related information and remove overlap, and **preserve ALL unique and important information**. If a concept is truly essential for context in a new section, re-explain it *briefly and concisely*, but **under no circumstances repeat full definitions or lengthy explanations** if they have already been thoroughly covered in a previous section of the same topic. **CRITICAL: The goal is to expand explanations without introducing any redundancy.**\n"
    "6.  **Avoid Generic Sections:** **ABSOLUTELY AVOID GENERIC INTRODUCTORY SECTIONS** like 'Concepts:', 'Definitions:', 'Key Facts:', or 'Tort Law Summary' at the beginning of each chunk's notes. Start directly with the specific topics and explanations relevant to *this particular chunk*.\n"
    "7.  **Detailed and Expanded Explanations:** Provide *exceptionally clear and thoroughly detailed explanations* for all concepts, ensuring they are very easy to understand and fully adequate for exam preparation. *Expand on points as necessary to provide complete understanding, elaborating sufficiently to cover all nuances and implications*, but avoid unnecessary verbosity by integrating information smoothly.\n"
    "8.  **Organized Sub-headings:** Organize notes with clear sub-headings (e.g., '## Topics:', '### [Sub-sub-topic Title]'). CRITICAL: Ensure that sub-headings are correctly formatted and ABSOLUTELY DO NOT contain extra '##' symbols mistakenly (e.g., '### ## Topic' is incorrect; it should be '### Topic').\n"
    "9.  **Bullet Points and Examples:** Use detailed bullet points ('- '), clear explanations ('*Explanation:*'), and relevant examples ('*Examples:*' followed by bullet points). Generate examples *only if they are absolutely essential for clarifying a concept and are not already explicitly provided in the original text*. Ensure generated examples are concise and directly illustrate the point.\n"
    "10. **No Example Headings:** CRITICAL: DO NOT use '### Examples:' or '## Examples:' as a heading. If examples are provided, integrate them under relevant sub-headings or use a lower-level heading like '### Examples:'.\n"
    "11. **Exclude Code:** EXCLUDE any programming code snippets unless they are directly part of the legal text (e.g., a specific code of law, not a programming example).\n"
    "12. **No Prompt in Output:** DO NOT include any part of this prompt in your output. ONLY provide the structured notes.\n"
    "13. **No YAML:** CRITICAL: DO NOT generate any YAML front matter (e.g., lines starting and ending with '---') or any content that could be misinterpreted as YAML metadata. Avoid using '---' as a separator within the notes.\n\n"
    "{additional_context}" # Placeholder for additional context
    "MASTER BRAIN:\n{master_brain}\n\nCHAPTER TEXT:\n{chunk}\n"
)
