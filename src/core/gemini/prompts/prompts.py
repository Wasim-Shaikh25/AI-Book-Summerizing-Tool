# Common prompt templates for various LLM operations

PROMPT_CORE_IDEAS = (
    "Extract the most important concepts, definitions, formulas, examples, and key facts "
    "from the text below as detailed and comprehensive bullet points, ensuring thoroughness for exam revision.\n\n"
    "TEXT:\n{text}"
)

PROMPT_MASTER_BRAIN_COMBINE_BLOCKS = (
    "Combine and organize the following concise bullet groups into one organized short knowledge block. "
    "Group related points and keep important examples.\n\n{text}"
)

PROMPT_MASTER_BRAIN_FINAL = (
    "You are a MASTER KNOWLEDGE BRAIN. Combine the following organized blocks into a single comprehensive master summary "
    "organized by topics, with detailed explanations, clear bullet points, and relevant examples where useful. Use simple English.\n\n{text}"
)

PROMPT_REWRITE_CHUNK = (
    "Based on the MASTER BRAIN knowledge, rewrite the following CHAPTER TEXT into *clear, sufficiently detailed, and exam-focused* notes, using simple English.\n"
    "**CRITICAL INSTRUCTIONS FOR TITLES AND STRUCTURE (STRICT ADHERENCE REQUIRED):**\n"
    "1.  **Chapter Titles (Main Topics):** Generate a *unique, highly specific, and direct* chapter title. This title should be a precise, overarching topic for the content of THIS CHUNK, and serve as a parent topic under which related sub-topics can be grouped. Format it as a **single '#' followed by the title text** (e.g., '# Tort Law Principles'). ABSOLUTELY DO NOT use generic or thematic phrases like 'Understanding', 'Introduction to', 'Overview of', or the overall theme (e.g., 'Contracts in Different Jurisdictions'). For example, instead of 'Understanding Contracts under Indian Law', use 'Contracts under Indian Law'.\n"
    "2.  **Sub-topic Titles:** If the content of this chunk is a sub-topic or continuation of an existing broader chapter (as indicated in `EXISTING_TOP_LEVEL_CHAPTER_TITLES` in `additional_context`), then propose a sub-topic title that fits logically under that existing chapter. Format it as **two '##' followed by the title text** (e.g., '## Elements of Negligence'). The goal is to group all related information under one main chapter, using sub-headings for distinct aspects.\n"
    "3.  **STRICT TITLE FORMATTING - NO EXTRA HASHES OR PREFIXES:** When generating titles, ONLY output the title text after the '#' or '##'. DO NOT include any prefixes like 'Chapter Title:' or 'Sub-topic Title:' in your output. For example, for a main chapter, output '# My Chapter Title', not '# Chapter Title: My Chapter Title'. For a sub-topic, output '## My Sub-topic Title', not '## Sub-topic Title: My Sub-topic Title'. **ENSURE there are ABSOLUTELY NO extra '#' characters in your headings** (e.g., '## # Topic' or '### ## Topic' are incorrect; it must be exactly '# Topic' or '## Sub-topic').\n"
    "4.  **Summary:** Provide a concise yet informative '**Summary:**' that *precisely reflects the core content of this individual chapter text*.\n"
    "5.  **Avoid Repetition:** **STRICTLY AVOID REPEATING INFORMATION** already covered in the 'Master Brain' or earlier in the generated notes for this chapter. Focus on presenting new, distinct, and relevant details for this specific chunk. Combine related information under appropriate headings to prevent redundancy.\n"
    "6.  **Avoid Generic Sections:** **ABSOLUTELY AVOID GENERIC INTRODUCTORY SECTIONS** like 'Concepts:', 'Definitions:', 'Key Facts:', or 'Tort Law Summary' at the beginning of each chunk's notes. Start directly with the specific topics and explanations relevant to *this particular chunk*.\n"
    "7.  **Detailed Explanations:** Provide *clear and sufficiently detailed explanations* for all concepts, ensuring they are easy to understand and adequate for exam preparation. Balance conciseness with necessary depth.\n"
    "8.  **Organized Sub-headings:** Organize notes with clear sub-headings (e.g., '## Topics:', '### [Sub-sub-topic Title]'). CRITICAL: Ensure that sub-headings are correctly formatted and ABSOLUTELY DO NOT contain extra '##' symbols mistakenly (e.g., '### ## Topic' is incorrect; it should be '### Topic').\n"
    "9.  **Bullet Points and Examples:** Use detailed bullet points ('- '), clear explanations ('*Explanation:*'), and relevant examples ('*Examples:*' followed by bullet points). Generate examples *only if they are absolutely essential for clarifying a concept and are not already explicitly provided in the original text*. Ensure generated examples are concise and directly illustrate the point.\n"
    "10. **No Example Headings:** CRITICAL: DO NOT use '### Examples:' or '## Examples:' as a heading. If examples are provided, integrate them under relevant sub-headings or use a lower-level heading like '### Examples:'.\n"
    "11. **Exclude Code:** EXCLUDE any programming code snippets unless they are directly part of the legal text (e.g., a specific code of law, not a programming example).\n"
    "12. **No Prompt in Output:** DO NOT include any part of this prompt in your output. ONLY provide the structured notes.\n"
    "13. **No YAML:** CRITICAL: DO NOT generate any YAML front matter (e.g., lines starting and ending with '---') or any content that could be misinterpreted as YAML metadata. Avoid using '---' as a separator within the notes.\n\n"
    "{additional_context}" # Placeholder for additional context
    "MASTER BRAIN:\n{master_brain}\n\nCHAPTER TEXT:\n{chunk}\n"
)
