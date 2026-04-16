import httpx
import json
import base64
import os

class OllamaClient:
    def __init__(self, base_url="http://localhost:11434"):
        self.base_url = base_url

    async def generate(self, model, prompt, images=None, system=None):
        """
        Calls Ollama generate API with keep_alive=0 to ensure model is unloaded immediately.
        """
        url = f"{self.base_url}/api/generate"
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": 0  # Force unload immediately after response
        }
        
        if system:
            payload["system"] = system
            
        if images:
            # images should be a list of base64 strings
            payload["images"] = images

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return response.json().get("response", "")
            except Exception as e:
                return f"Error calling Ollama ({model}): {str(e)}"

# Singleton instance
ollama = OllamaClient()
