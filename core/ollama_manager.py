import subprocess
import time
import httpx
import logging
import os
import asyncio

class OllamaOnDemandManager:
    def __init__(self, port=11434, model="llama3.2:1b"):
        self.port = port
        self.model = model
        self.base_url = f"http://127.0.0.1:{port}"

    def _run_local(self, command):
        """Runs commands natively inside the Debian sandbox."""
        try:
            subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            logging.error(f"[!] Ollama Local Error: {e}")
            return False

    async def start_service(self):
        """Starts the Ollama server inside Debian."""
        logging.info("[*] Awakening Llama (Starting Ollama service)...")
        self._run_local(f"OLLAMA_HOST=127.0.0.1:{self.port} ollama serve > /dev/null 2>&1 &")
        
        max_retries = 10
        async with httpx.AsyncClient() as client:
            for i in range(max_retries):
                try:
                    resp = await client.get(self.base_url)
                    if resp.status_code == 200:
                        logging.info("[*] Llama is awake and ready.")
                        return True
                except:
                    pass
                await asyncio.sleep(1)
        logging.error("[!] Failed to awaken Llama locally.")
        return False

    async def stop_service(self):
        """Kills the Ollama server inside Debian to free RAM."""
        logging.info("[*] Putting Llama to sleep...")
        subprocess.run("pkill -9 -f ollama", shell=True)
        logging.info("[*] Llama is now sleeping. RAM freed.")

    async def generate(self, prompt, system_prompt=None):
        started = await self.start_service()
        if not started:
            return "Lỗi: Không thể khởi động trí tuệ cục bộ."

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False
                }
                if system_prompt:
                    payload["system"] = system_prompt
                
                logging.info(f"[*] Llama is thinking... (Model: {self.model})")
                resp = await client.post(f"{self.base_url}/api/generate", json=payload)
                result = resp.json().get("response", "Không nhận được phản hồi từ Llama.")
                return result
        except Exception as e:
            return f"Lỗi khi xử lý với Llama: {str(e)}"
        finally:
            await self.stop_service()
