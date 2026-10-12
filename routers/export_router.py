import jwt
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from core.auth import decode_download_token
from mcp_tools.export import EXPORT_DIR

router = APIRouter(prefix="/export", tags=["export"])


# 链接本身就是凭证：token 里签了文件名和过期时间，浏览器直接打开就能下载，不需要再带登录态
@router.get("/download")
async def download_export(token: str):
    try:
        file, name = decode_download_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="下载链接已过期，请重新导出")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="下载链接无效")

    path = EXPORT_DIR / file
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    return FileResponse(
        path,
        filename=name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
