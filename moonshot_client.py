import os, json, requests
from typing import Dict, Any

class MoonshotClient:
    def __init__(self, base_url: str = "https://api.moonshot.ai/v1", model: str = "kimi-k2-turbo-preview", temperature: float = 0.35, max_tokens: int = 300):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        api_key = os.environ.get("MOONSHOT_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("MOONSHOT_API_KEY not set.")
        self.api_key = api_key

    def chat_json(self, system_prompt: str, user_content: str, timeout_s: float = 20.0) -> Dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]
        }
        r = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"].strip()

        # strict JSON salvage
        try:
            return json.loads(content)
        except Exception:
            a = content.find("{")
            b = content.rfind("}")
            if a >= 0 and b > a:
                return json.loads(content[a:b+1])
            raise
