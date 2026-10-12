"""运营数据 MCP 服务，挂载在 main.py 的 /ai 下，地址是 /ai/mcp。

请求头要带 /user/login 签发的 JWT：Authorization: Bearer <token>
"""

import jwt
from fastmcp import FastMCP
from fastmcp.server.auth import TokenVerifier
from fastmcp.server.auth.auth import AccessToken

from core.auth import decode_access_token
from mcp_tools.export import export_orders, get_export_status
from mcp_tools.order import get_order_detail
from mcp_tools.product import get_all_products
from mcp_tools.stats import query_overview, query_ranking, query_trend


class JwtTokenVerifier(TokenVerifier):
    """每个 HTTP 请求都会调用。返回 None 时 FastMCP 直接回 401，请求到不了工具。"""

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            user_id = decode_access_token(token)
        except jwt.InvalidTokenError:
            return None
        return AccessToken(token=token, client_id=str(user_id), scopes=[])


mcp = FastMCP(
    name="biz-data",
    auth=JwtTokenVerifier(),
    tools=[
        get_order_detail, get_all_products, export_orders, get_export_status,
        query_overview, query_trend, query_ranking,
    ],
)

# 无状态模式：每个请求独立处理，多实例部署时不用做会话保持
mcp_app = mcp.http_app(stateless_http=True)
