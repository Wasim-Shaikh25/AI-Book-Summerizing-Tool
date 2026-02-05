import logging
import re
import json
import google.generativeai as genai
from typing import Any, Dict, Optional, Type, Union
from pydantic import BaseModel, ValidationError
from src.config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

class GeminiClient:
    """
    A centralized, production-grade client for interacting with Google Gemini.
    Supports schema-driven generation and robust error handling.
    """
    def __init__(self, model_name: str = GEMINI_MODEL):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not found in environment variables.")
        
        genai.configure(api_key=GEMINI_API_KEY)
        self.model_name = model_name
        self.model = genai.GenerativeModel(model_name)
        logger.info(f"GeminiClient initialized with model: {model_name}")

    def generate_content(
        self, 
        prompt: str, 
        generation_config: Optional[Dict[str, Any]] = None,
        response_schema: Optional[Type[BaseModel]] = None
    ) -> Union[str, Dict[str, Any]]:
        """
        Generates content from Gemini (Synchronous). If response_schema is provided, 
        it enforces JSON output and validates it against the schema.
        """
        config = generation_config or {
            "temperature": 0.1,
            "top_p": 1,
            "top_k": 1,
        }

        if response_schema:
            config["response_mime_type"] = "application/json"

        try:
            response = self.model.generate_content(prompt, generation_config=config)
            
            if not response or not response.text:
                logger.error("Gemini returned an empty response.")
                return "" if not response_schema else {}

            raw_text = response.text.strip()
            
            if response_schema:
                return self._parse_and_validate(raw_text, response_schema)
            
            return raw_text

        except Exception as e:
            logger.error(f"Error during Gemini generation: {str(e)}")
            if response_schema:
                return {}
            return ""

    async def generate_content_async(
        self, 
        prompt: str, 
        generation_config: Optional[Dict[str, Any]] = None,
        response_schema: Optional[Type[BaseModel]] = None
    ) -> Union[str, Dict[str, Any]]:
        """
        Generates content from Gemini (Asynchronous). If response_schema is provided, 
        it enforces JSON output and validates it against the schema.
        """
        config = generation_config or {
            "temperature": 0.1,
            "top_p": 1,
            "top_k": 1,
        }

        if response_schema:
            config["response_mime_type"] = "application/json"

        try:
            response = await self.model.generate_content_async(prompt, generation_config=config)
            
            if not response or not response.text:
                logger.error("Gemini returned an empty response.")
                return "" if not response_schema else {}

            raw_text = response.text.strip()
            
            if response_schema:
                return self._parse_and_validate(raw_text, response_schema)
            
            return raw_text

        except Exception as e:
            logger.error(f"Error during Gemini async generation: {str(e)}")
            if response_schema:
                return {}
            return ""

    def _parse_and_validate(self, text: str, schema: Type[BaseModel]) -> Dict[str, Any]:
        """Parses JSON text and validates it against a Pydantic schema, with recovery."""
        cleaned_text = text
        
        # 1. Fence Stripping
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text.split("```json")[1].split("```")[0].strip()
        elif cleaned_text.startswith("```"):
            cleaned_text = cleaned_text.split("```")[1].split("```")[0].strip()

        # 2. Trailing Comma Cleanup
        # This regex finds a comma followed by optional whitespace and then a closing bracket or brace
        cleaned_text = re.sub(r',\s*([\]}])', r'\1', cleaned_text)

        try:
            data = json.loads(cleaned_text)
            validated_data = schema.model_validate(data)
            return validated_data.model_dump()
        except json.JSONDecodeError as e:
            logger.warning(f"Initial JSON decode failed: {e}. Attempting newline escaping...")
            # 3. Newline Escaping (if initial parse fails)
            # This heuristic attempts to fix unescaped newlines within string values.
            # It replaces newlines that are not part of the JSON structure.
            escaped_text = re.sub(r'(?<!\\)\n', r'\\n', cleaned_text)
            try:
                data = json.loads(escaped_text)
                validated_data = schema.model_validate(data)
                return validated_data.model_dump()
            except (json.JSONDecodeError, ValidationError) as e_recovery:
                logger.error(f"JSON validation failed even after newline escaping: {str(e_recovery)}")
                logger.debug(f"Raw text that failed validation: {text}")
                logger.debug(f"Cleaned text that failed validation: {cleaned_text}")
                logger.debug(f"Escaped text that failed validation: {escaped_text}")
                return {}
        except ValidationError as e:
            logger.error(f"Pydantic validation failed: {str(e)}")
            logger.debug(f"Raw text that failed validation: {text}")
            logger.debug(f"Cleaned text that failed validation: {cleaned_text}")
            return {}
