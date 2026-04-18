import asyncio
import logging
import sys
from core.mcp_manager import MCPManager

logging.basicConfig(level=logging.INFO)

async def test_mcp():
    print("[*] Khởi tạo MCP Manager...")
    mcp = MCPManager()
    
    # Thử kết nối tới server 'fetch' mẫu (yêu cầu npx/node)
    print("[*] Đang kết nối tới MCP Server: fetch (qua npx)...")
    success = await mcp.connect_to_server(
        "fetch", 
        "npx", 
        ["-y", "@modelcontextprotocol/server-fetch"]
    )
    
    if not success:
        print("[!] Không thể kết nối tới MCP Server. Vui lòng đảm bảo đã cài 'npx' và thư viện 'mcp'.")
        return

    print("[*] Danh sách các công cụ MCP tìm thấy:")
    tools = await mcp.get_all_tools()
    for tool in tools:
        print(f" - {tool.name}: {tool.description}")

    # Chạy thử một lệnh fetch nếu có
    if any(t.name == "fetch" for t in tools):
        print("\n[*] Chạy thử nghiệm công cụ 'fetch' với trang google.com...")
        result = await mcp.execute_tool("fetch", {"url": "https://www.google.com"})
        print(f"[*] Kết quả (200 ký tự đầu): \n{result[:200]}...")

    await mcp.close_all()
    print("\n[*] Thử nghiệm kết thúc.")

if __name__ == "__main__":
    asyncio.run(test_mcp())
