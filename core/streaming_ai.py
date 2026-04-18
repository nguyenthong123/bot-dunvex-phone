import os
import asyncio
import logging
import json
import re
from openai import AsyncOpenAI
from core.ai import AIOrchestrator

class StreamingOrchestrator(AIOrchestrator):
    """
    Enhanced Orchestrator that supports streaming reasoning and content.
    Includes Professional Suppressing of large code blocks for Telegram.
    """
    
    def _extract_tool_args(self, raw_args):
        """
        Robustly extracts arguments from a tool call string.
        Gracefully handles truncated / unclosed quoted strings.
        """
        args = []
        # Find all fully closed quoted strings first
        pattern = r'"((?:[^"\\]|\\.)*)"'
        matches = re.findall(pattern, raw_args, re.DOTALL)
        
        # If we found matches, clean them up
        for m in matches:
            # Better unescaping for complex JSON-like output
            try:
                # Try to load as JSON to handle all escapes properly
                clean_m = json.loads(f'"{m}"')
            except:
                # Fallback to manual replacement
                clean_m = m.replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t').replace('\\\\', '\\')
            args.append(clean_m)
            
        # GRACEFUL TRUNCATION: If we have one arg (path) but the text clearly continues,
        # it means the second arg (massive code) was cut off before its final quote.
        if len(args) == 1 and ',"' in raw_args:
            # Re-search for the start of the second argument
            # We look for everything after the comma and the first quote of the 2nd arg
            parts = raw_args.split(',"', 1)
            if len(parts) > 1:
                truncated_part = parts[1]
                # If there's no closing quote for this part, take it all
                if not truncated_part.endswith('"'):
                    # Strip any trailing structures that might exist but were caught partially
                    clean_truncated = truncated_part.rstrip(')] ')
                    args.append(clean_truncated)
            
        return args

    def _fix_virtual_path(self, path):
        """
        Maps virtual paths to ACTUAL Termux paths with STRICT ISOLATION.
        Prevents access to the 15GB monster in the parent home directory.
        """
        virtual_prefix = "/home/agent-workspace/"
        actual_prefix = "/data/data/com.termux/files/home/open-claw-source/"
        
        # 1. CLEANING: Remove path traversal attacks
        path = path.replace("../", "").replace("..\\", "").strip("/")
        
        # 2. MAPPING: If it's a virtual path, remap it
        if path.startswith("home/agent-workspace/"):
            path = path.replace("home/agent-workspace/", "")
        elif path.startswith(virtual_prefix.strip("/")):
            path = path.replace(virtual_prefix.strip("/"), "")
            
        # 3. LOCKDOWN: Force path to be inside actual_prefix
        # If the path is already absolute and outside, we force it back
        if path.startswith("/data/data/com.termux/files/home/") and not path.startswith(actual_prefix):
            logging.warning(f"[!] Path Escape Attempt Detected: {path}. Forcing Lockdown.")
            return os.path.join(actual_prefix, os.path.basename(path))
            
        # Standard relative path join
        return os.path.join(actual_prefix, path)

    def _find_balanced_tool_call(self, text):
        """
        Finds the first [CALL: ...] block. If the stream ended without a closing ']',
        it performs a 'Best Effort' extraction to save as much as possible.
        """
        start_tag = "[CALL:"
        start_idx = text.find(start_tag)
        if start_idx == -1:
            return None, None
            
        depth = 0
        end_idx = -1
        # Track bracket depth
        for i in range(start_idx, len(text)):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    end_idx = i
                    break
        
        # BEST EFFORT / GRACEFUL TRUNCATION
        if end_idx == -1:
            # If the block was never closed, we take the entire remaining text
            # This handles mid-stream cuts (120s/300s timeouts)
            call_block = text[start_idx:]
        else:
            call_block = text[start_idx:end_idx+1]
        
        # Extract tool name and raw arguments
        # We try strict matching first, then fallback to partial matching
        strict_match = re.search(r"\[CALL:\s*(\w+)\s*\((.*)\)\]", call_block, re.DOTALL)
        if strict_match:
             return strict_match.group(1).strip(), strict_match.group(2).strip()
             
        # FALLBACK: Partial match for truncated calls
        # Pattern: [CALL: name(args...
        partial_match = re.search(r"\[CALL:\s*(\w+)\s*\((.*)", call_block, re.DOTALL)
        if partial_match:
             return partial_match.group(1).strip(), partial_match.group(2).strip()
             
        return None, None

    async def get_response_stream(self, user_id, user_text, image_path=None):
        """
        Async Generator that yields interaction events:
        - ('thought', chunk): DeepSeek R1 reasoning chunks
        - ('content', chunk): Final answer chunks
        - ('tool_start', name): Tool execution began
        - ('tool_end', result): Tool execution finished
        """
        await self._ensure_mcp_init()
        
        api_key = self.memory.get_setting("DEEPSEEK_API_KEY", os.getenv("DEEPSEEK_API_KEY"))
        base_url = self.memory.get_setting("OPENAI_API_BASE", os.getenv("OPENAI_API_BASE", "https://api.deepseek.com"))

        if not self.client:
            self.client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url
            )

        history_list = self.memory.get_chat_history(user_id, limit=10)
        messages = [{"role": "system", "content": await self._get_system_prompt()}]
        
        for msg in history_list:
            role = msg.get("role")
            content = msg.get("content", "")
            messages.append({"role": role, "content": self._truncate_text(content, max_chars=5000)})
        
        current_content = user_text
        if image_path:
            try:
                yield ('status', "👁️ Đang phân tích hình ảnh...")
                image_description = await self.tools.analyze_local_image(image_path, "Mô tả chi tiết nội dung hình ảnh.")
                current_content = f"[KẾT QUẢ THỊ GIÁC NỘI BỘ]: {image_description}\n---\nYÊU CẦU NGƯỜI DÙNG: {user_text}"
            except Exception as v_e:
                logging.error(f"[!] Vision Error: {v_e}")
                current_content += f"\n[Lỗi phân tích ảnh: {v_e}]"
        
        # Truncate content to prevent 400 Bad Request (Max ~100k chars for safety)
        safe_content = current_content[:100000] + "... [Dữ liệu quá lớn đã bị cắt tỉa]" if len(current_content) > 100000 else current_content
        messages.append({"role": "user", "content": safe_content})
        
        full_ai_output = ""
        last_yielded_len = 0
        followup_count = 0
        max_loops = 15
        for loop_idx in range(max_loops):
            yield ('status', f"🧠 Đang điều phối (Bước {loop_idx + 1})...")
            
            current_loop_content = ""
            current_loop_reasoning = ""
            is_suppressed = False
            thought_yielded_chars = 0
            
            try:
                # Optimized for R1 with 8k tokens and 120s timeout
                stream = await self.client.chat.completions.create(
                    model="deepseek-reasoner",
                    messages=messages,
                    max_tokens=8192,
                    stream=True,
                    timeout=600.0
                )
                
                async for chunk in stream:
                    if not chunk.choices: continue
                    delta = chunk.choices[0].delta
                    
                    # Handle Reasoning Content with Truncation
                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        rc = delta.reasoning_content
                        current_loop_reasoning += rc
                        if thought_yielded_chars < 3000:
                            yield ('thought', rc)
                            thought_yielded_chars += len(rc)
                        elif thought_yielded_chars == 3000:
                            yield ('thought', "\n... [Suy luận chuyên sâu đang tiếp tục ngầm]")
                            thought_yielded_chars += 1
                    
                    # Handle Final Content with Strict Suppression
                    if hasattr(delta, 'content') and delta.content:
                        c = delta.content
                        current_loop_content += c
                        
                        # DETECTION: Once suppressed, stay suppressed for this loop
                        if not is_suppressed:
                            # 1. Detect Planning Block [KẾ HOẠCH]
                            if "[KẾ HOẠCH]" in current_loop_content:
                                plan_match = re.search(r"\[KẾ HOẠCH\](.*?)(\[CALL:|$|```)", current_loop_content, re.DOTALL)
                                if plan_match:
                                    plan_text = plan_match.group(1).strip()
                                    if plan_text:
                                        yield ('status', f"📝 KẾ HOẠCH: {plan_text[:200]}...")

                            # 2. Detect tool call markers or block starters
                            if "[CALL:" in current_loop_content or "```" in c:
                                is_suppressed = True
                                yield ('status', "🛠️ Đang thực thi các tác vụ kỹ thuật...")
                            # 3. Detect code heuristics (HTML Tags, Escaped chars, CSS)
                            elif len(current_loop_content) > 50:
                                code_markers = ["<div", "<nav", "class=", "href=", "<!--", "\\n", "\\\""]
                                if any(marker in current_loop_content for marker in code_markers) or \
                                   any(char in c for char in ["{", "}", "$", "import"]):
                                    is_suppressed = True
                                    yield ('status', "🛠️ Đang biên dịch mã nguồn hệ thống...")

                        if not is_suppressed:
                            yield ('content', c)
                        else:
                            # Yield periodic status for high-volume technical tasks
                            if len(current_loop_content) - last_yielded_len > 2000:
                                yield ('status', f"⚙️ Đang xử lý khối dữ liệu lớn ({len(current_loop_content)//1024} KB)...")
                                last_yielded_len = len(current_loop_content)

                # Combine
                full_ai_output += current_loop_content

                # NEW: Auto-Followup for empty content after long reasoning (Hard-Limited)
                if not current_loop_content and current_loop_reasoning:
                    if followup_count < 2:
                        followup_count += 1
                        logging.info(f"[*] Auto-Followup triggered (Attempt {followup_count}/2).")
                        # Truncate reasoning context for the assistant message
                        safe_reasoning = current_loop_reasoning[:1000] + "... [Suy luận quá dài đã bị cắt]" if len(current_loop_reasoning) > 1000 else current_loop_reasoning
                        messages.append({"role": "assistant", "content": f"[THOUGHTS]: {safe_reasoning}"})
                        messages.append({"role": "user", "content": "Dựa trên suy luận của bạn, hãy cung cấp kết quả cuối cùng hoặc thực thi các công cụ cần thiết."})
                        continue
                    else:
                        logging.warning("[!] Max followups reached. Breaking loop.")
                        break

                # BALANCED TOOL EXTRACTION
                tool_name, raw_args = self._find_balanced_tool_call(current_loop_content)
                
                if tool_name:
                    yield ('tool_start', tool_name)
                    args = self._extract_tool_args(raw_args)
                    
                    # Fix path for write_file / read_file
                    if tool_name in ["write_file", "read_file", "list_files"] and args:
                        args[0] = self._fix_virtual_path(args[0])

                    try:
                        if tool_name in self.tools.get_available_tool_names():
                            result = await self.tools.execute_tool(tool_name, args)
                            
                            # SELF-HEALING: Verify write_file result
                            if tool_name == "write_file":
                                target_file = args[0]
                                if os.path.exists(target_file):
                                    size = os.path.getsize(target_file)
                                    if size == 0:
                                        logging.warning(f"[!] Self-Healing: Detected 0-byte file at {target_file}")
                                        yield ('status', "⚠️ Phát hiện tệp rỗng! Đang tự động xử lý lại...")
                                        result = "[LỖI TỰ KIỂM TRA]: Tệp vừa ghi bị 0-byte. Bạn có thể đã bị Timeout. Hãy THỰC HIỆN LẠI lệnh write_file với nội dung ĐẦY ĐỦ ngay lập tức."
                        elif tool_name in self.mcp.tools_map:
                            mcp_args = {}
                            available_mcp_tools = await self.mcp.get_all_tools()
                            target_tool = next((t for t in available_mcp_tools if t.name == tool_name), None)
                            if target_tool and hasattr(target_tool, 'inputSchema'):
                                properties = target_tool.inputSchema.get('properties', {})
                                prop_names = list(properties.keys())
                                for i, val in enumerate(args):
                                    if i < len(prop_names): mcp_args[prop_names[i]] = val
                            result = await self.mcp.execute_tool(tool_name, mcp_args)
                        else:
                            result = f"Lỗi: Không tìm thấy công cụ '{tool_name}'."
                        
                        yield ('tool_end', result)
                        
                        # 50K SHIELD: Absolute protection against Token Overflow (400 Bad Request)
                        safe_result = str(result)
                        if len(safe_result) > 50000:
                            logging.warning(f"[!] Tool output too large ({len(safe_result)} chars). Truncating to 50k.")
                            safe_result = safe_result[:50000] + "\n\n... [KẾT QUẢ QUÁ LỚN - ĐÃ CẮT TỈA 50K CHARS ĐỂ BẢO VỆ BỘ NHỚ] ..."
                            
                        messages.append({"role": "assistant", "content": current_loop_content})
                        messages.append({"role": "user", "content": f"[KẾT QUẢ HỆ THỐNG]: {safe_result}"})
                        continue
                    except Exception as tool_e:
                        logging.error(f"[!] Tool Runtime Error: {tool_e}")
                        yield ('tool_end', f"Lỗi thực thi: {tool_e}")
                        messages.append({"role": "assistant", "content": current_loop_content})
                        messages.append({"role": "user", "content": f"[LỖI HỆ THỐNG]: {tool_e}"})
                        continue
                
                break

            except Exception as e:
                logging.error(f"[!] Streaming Error: {e}")
                yield ('error', f"Lỗi luồng AI: {str(e)}")
                break
        
        # Save to memory at the end
        self.memory.add_chat(user_id, "user", user_text)
        
        # FINAL SANITIZATION: If suppressed during loop, don't leak the raw dump as final answer
        if is_suppressed and not any(m in full_ai_output for m in ["[KẾT QUẢ]", "Dưới đây là"]):
            clean_output = "Nhiệm vụ kỹ thuật đã được thực hiện thành công vào hệ thống tệp."
        else:
            clean_output = full_ai_output

        self.memory.add_chat(user_id, "assistant", clean_output if clean_output else "(Tiến trình hoàn tất)")
        yield ('done', clean_output)
