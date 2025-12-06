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
    "Generate a *unique, highly specific, and direct* '# Chapter Title:' and a concise yet informative '**Summary:**' that *precisely reflects the core content of this individual chapter text*.\n"
    "CRITICAL: The '# Chapter Title:' MUST be a precise, standalone topic. ABSOLUTELY DO NOT use generic or thematic phrases like 'Understanding', 'Introduction to', 'Overview of', or the overall theme (e.g., 'Contracts in Different Jurisdictions') in the chapter title or summary. For example, instead of 'Understanding Contracts under Indian Law', use 'Contracts under Indian Law'.\n"
    "STRICTLY ENSURE that the chapter title is a direct, descriptive heading for the content of THIS CHUNK ONLY, and does not contain any introductory words like 'Understanding'.\n"
    "Furthermore, ENSURE THE CHAPTER TITLE IS UNIQUE ACROSS ALL CHAPTERS and specifically reflects the distinct content of this chunk, avoiding any repetition of titles from other potential chapters.\n"
    "Provide *clear and sufficiently detailed explanations* for all concepts, ensuring they are easy to understand and adequate for exam preparation. Balance conciseness with necessary depth.\n"
    "Organize notes with clear sub-headings (e.g., '## Topics:', '## [Topic Title]:'). Ensure that sub-headings are correctly formatted and do not contain extra '##' symbols mistakenly.\n"
    "Use detailed bullet points ('- '), clear explanations ('*Explanation:*'), and relevant examples ('*Examples:*' followed by bullet points).\n"
    "Generate examples *only if they are absolutely essential for clarifying a concept and are not already explicitly provided in the original text*. Ensure generated examples are concise and directly illustrate the point.\n"
    "CRITICAL: DO NOT use '### Examples:' or '## Examples:' as a heading. If examples are provided, integrate them under relevant sub-headings or use a lower-level heading like '### Examples:'.\n"
    "EXCLUDE any programming code snippets unless they are directly part of the legal text (e.g., a specific code of law, not a programming example).\n"
    "Avoid repeating information already covered in the 'Master Brain' or earlier in the generated notes for this chapter.\n"
    "DO NOT include any part of this prompt in your output. ONLY provide the structured notes.\n"
    "CRITICAL: DO NOT generate any YAML front matter (e.g., lines starting and ending with '---') or any content that could be misinterpreted as YAML metadata. Avoid using '---' as a separator within the notes.\n\n"
    "{additional_context}" # Placeholder for additional context
    "MASTER BRAIN:\n{master_brain}\n\nCHAPTER TEXT:\n{chunk}\n"
)
