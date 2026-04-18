import asyncio
import logging
from contextlib import AsyncExitStack
from typing import Dict, List, Any, Optional

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    HAS_MCP = True
except ImportError:
    HAS_MCP = False

logger = logging.getLogger(__name__)

class MCPManager:
    def __init__(self):
        self.sessions: Dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()
        self.tools_map: Dict[str, str] = {} # tool_name -> server_name
        self.is_initialized = False

    async def connect_to_server(self, name: str, command: str, args: List[str]):
        """Connect to an MCP server via stdio."""
        if not HAS_MCP:
            logger.error("MCP library not installed. Cannot connect to server.")
            return False

        try:
            server_params = StdioServerParameters(command=command, args=args)
            transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
            session = await self.exit_stack.enter_async_context(ClientSession(transport[0], transport[1]))
            
            # Add timeout to initialize to prevent hangs
            await asyncio.wait_for(session.initialize(), timeout=30.0)
            self.sessions[name] = session
            logger.info(f"[*] Connected to MCP server: {name}")
            
            # Refresh tools map
            await self._refresh_tools_map()
            return True
        except asyncio.TimeoutError:
            logger.error(f"[!] Connection to MCP server {name} timed out.")
            return False
        except Exception as e:
            logger.error(f"[!] Failed to connect to MCP server {name}: {e}")
            return False

    async def _refresh_tools_map(self):
        """Update the mapping of tool names to their respective servers."""
        self.tools_map = {}
        for name, session in self.sessions.items():
            try:
                # Add timeout to list_tools
                tools_result = await asyncio.wait_for(session.list_tools(), timeout=30.0)
                for tool in tools_result.tools:
                    if tool.name in self.tools_map:
                        logger.warning(f"[!] Duplicate tool name found: {tool.name}. Overwriting with {name}")
                    self.tools_map[tool.name] = name
            except Exception as e:
                logger.error(f"[!] Failed to list tools for {name}: {e}")

    async def get_all_tools(self) -> List[Any]:
        """Fetch all available tools from all connected MCP servers."""
        all_tools = []
        for name, session in self.sessions.items():
            try:
                tools_result = await session.list_tools()
                all_tools.extend(tools_result.tools)
            except Exception as e:
                logger.error(f"[!] Failed to fetch tools from {name}: {e}")
        return all_tools

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Execute a tool on the appropriate MCP server."""
        server_name = self.tools_map.get(tool_name)
        if not server_name:
            return f"Error: Tool '{tool_name}' not found in any MCP server."

        session = self.sessions.get(server_name)
        if not session:
            return f"Error: Session for server '{server_name}' is inactive."

        try:
            logger.info(f"[*] Executing MCP tool: {tool_name} on {server_name}")
            result = await session.call_tool(tool_name, arguments)
            
            # MCP results can have multiple parts (text, image, etc.)
            # We join them into a single string for the AI
            text_parts = [content.text for content in result.content if hasattr(content, 'text')]
            return "\n".join(text_parts)
        except Exception as e:
            logger.error(f"[!] Error executing MCP tool {tool_name}: {e}")
            return f"Error executing tool {tool_name}: {str(e)}"

    async def close_all(self):
        """Close all active MCP sessions."""
        await self.exit_stack.aclose()
        self.sessions = {}
        self.tools_map = {}
        logger.info("[*] All MCP sessions closed.")
