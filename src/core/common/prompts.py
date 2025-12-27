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
    "You are a MASTER KNOWLEDGE BRAIN. Your task is to create a single, highly consolidated, and unique master summary "
    "from the following organized blocks. Follow these critical instructions:\n\n"
    "1.  **Intelligent Merging & De-duplication:** Carefully analyze all provided information. Intelligently combine related details and concepts from different blocks. If information is repeated across blocks, identify it and include it only once in the master brain. Do not repeat topics or information.\n"
    "2.  **Prioritize Uniqueness:** Extract and integrate all unique information present in the blocks. Ensure that the final master brain is a comprehensive synthesis, not just a concatenation.\n"
    "3.  **Structure & Clarity:** Organize the master brain by distinct, non-repetitive topics. Provide detailed explanations, use clear bullet points, and include relevant examples where useful. Ensure the language is simple English.\n"
    "4.  **Avoid Redundancy:** The ultimate goal is a 'one unique master' brain where every piece of information contributes without introducing redundancy or repeated topics.\n\n"
    "TEXT:\n{text}"
)

PROMPT_REWRITE_CHUNK = (
    "Based on the MASTER BRAIN knowledge, rewrite the following CHAPTER TEXT into *clear, sufficiently detailed, and exam-focused* notes, using simple English.\n"
"Generate a *highly specific, direct, and comprehensive* '# Chapter Title:' and a concise yet informative '**Summary:**' that *precisely reflects the core content of this individual chapter text*. The chapter title should serve as a parent topic or module under which related sub-topics can be grouped.\n"
"CRITICAL: The '# Chapter Title:' MUST be a precise, overarching topic. ABSOLUTELY DO NOT use generic or thematic phrases like 'Understanding', 'Introduction to', 'Overview of', or the overall theme (e.g., 'Contracts in Different Jurisdictions') in the chapter title or summary. For example, instead of 'Understanding Contracts under Indian Law', use 'Contracts under Indian Law'.\n"
"STRICTLY ENSURE that the chapter title is a direct, descriptive heading for the broader content that *this chunk contributes to*, and does not contain any introductory words like 'Understanding'.\n"
"Furthermore, ENSURE THE CHAPTER TITLE IS UNIQUE ACROSS ALL *TOP-LEVEL* CHAPTERS. If the content of this chunk is a sub-topic or a continuation of a previously established broader chapter, then instead of generating a new '# Chapter Title:', you should propose a '## Sub-topic Title:' that fits under the existing chapter. The goal is to group all related information under one main chapter, using sub-headings for distinct aspects.\n"
"If a suitable existing chapter title is provided in `additional_context` (specifically in `EXISTING_TOP_LEVEL_CHAPTER_TITLES`), and the content of this chunk is a sub-topic or a continuation of that existing chapter, then ABSOLUTELY DO NOT generate a new '# Chapter Title:'. Instead, propose a '## Sub-topic Title:' that fits logically under the existing chapter. The goal is to group all related information under one main chapter, using sub-headings for distinct aspects. If no suitable existing chapter is found in `EXISTING_TOP_LEVEL_CHAPTER_TITLES`, then generate a new unique '# Chapter Title:' that can serve as a parent topic.\n"
    "**ABSOLUTELY AVOID GENERIC INTRODUCTORY SECTIONS:** Do NOT include generic sections like 'Concepts:', 'Definitions:', 'Key Facts:', or 'Tort Law Summary' at the beginning of each chunk's notes. These are repetitive and do not add value to individual chapter notes. Start directly with the specific topics and explanations relevant to *this particular chunk*.\n"
    "Provide *clear and sufficiently detailed explanations* for all concepts, ensuring they are easy to understand and adequate for exam preparation. Balance conciseness with necessary depth.\n"
    "Organize notes with clear sub-headings (e.g., '## Topics:', '## [Topic Title]:'). CRITICAL: Ensure that sub-headings are correctly formatted and ABSOLUTELY DO NOT contain extra '##' symbols mistakenly (e.g., '### ## Topic' is incorrect; it should be '### Topic').\n"
    "Use detailed bullet points ('- '), clear explanations ('*Explanation:*'), and relevant examples ('*Examples:*' followed by bullet points).\n"
    "Generate examples *only if they are absolutely essential for clarifying a concept and are not already explicitly provided in the original text*. Ensure generated examples are concise and directly illustrate the point.\n"
    "CRITICAL: DO NOT use '### Examples:' or '## Examples:' as a heading. If examples are provided, integrate them under relevant sub-headings or use a lower-level heading like '### Examples:'.\n"
    "EXCLUDE any programming code snippets unless they are directly part of the legal text (e.g., a specific code of law, not a programming example).\n"
    "**STRICTLY AVOID REPEATING INFORMATION:** Do not repeat any information already covered in the 'Master Brain' or earlier in the generated notes for this chapter. Focus on presenting new, distinct, and relevant details for this specific chunk.\n"
    "DO NOT include any part of this prompt in your output. ONLY provide the structured notes.\n"
    "CRITICAL: DO NOT generate any YAML front matter (e.g., lines starting and ending with '---') or any content that could be misinterpreted as YAML metadata. Avoid using '---' as a separator within the notes.\n\n"
    "{additional_context}" # Placeholder for additional context
    "MASTER BRAIN:\n{master_brain}\n\nCHAPTER TEXT:\n{chunk}\n"
)

PROMPT_REVISION_NOTES = (
    "Rewrite the following content for the node '{node_title}' into *very short, concise, and revision-focused* notes, using simple English.\n"
    "Focus on extracting only the main points, key facts, and essential case details. Explanations should be extremely brief, just enough to convey the core concept for quick revision.\n"
    "**CRITICAL INSTRUCTIONS:**\n"
    "1.  **Conciseness:** Prioritize brevity. Every sentence should be packed with information, eliminating any verbose language.\n"
    "2.  **Main Points Only:** Extract only the most critical information. Do not elaborate unless absolutely necessary for clarity.\n"
    "3.  **Case Details Intact (Shortened):** If case details are present, keep them but summarize them to their absolute core, highlighting the key ruling or principle.\n"
    "4.  **No Repetition:** Do not repeat information already covered. Assume the user has a basic understanding and needs quick refreshers.\n"
    "5.  **Structure:** Use concise bullet points. Avoid lengthy paragraphs.\n"
    "6.  **Avoid Generic Headings:** Do not use generic introductory headings like 'Introduction', 'Overview', 'Concepts', 'Definitions'. Start directly with the content.\n"
    "7.  **Context of Explained Concepts:** Avoid re-explaining concepts listed in `explained_concepts_context`. Focus on new or deeper aspects.\n\n"
    "**Node Title:** {node_title}\n"
    "**Node Content:**\n{node_content}\n\n"
    "**Concepts Already Explained:**\n{explained_concepts_context}\n\n"
    "**Rewritten Revision Notes:**\n"
)
