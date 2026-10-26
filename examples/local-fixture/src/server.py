"""Synthetic local MCP transport fixture; never fetches any article or network URL."""
from fastmcp import FastMCP
mcp=FastMCP("Synthetic article fixture")
@mcp.tool
def read_weixin_article(url: str):
    return {"success":True,"title":"Synthetic transport demo","content":"This is original synthetic text used only to exercise the local MCP client transport. It is not a real WeChat article, and the received URL is never opened. "*3}
if __name__=="__main__":mcp.run(transport="stdio")
