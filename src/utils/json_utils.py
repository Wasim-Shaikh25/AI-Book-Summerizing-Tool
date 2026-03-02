import json


def safe_json_parse(text: str):
    try:
        return json.loads(text)
    except:
        return None
